from dataclasses import asdict, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from services import bot_profiles, profile_images
from services.bot_profiles import BotProfile, set_profile_image


class ProfileImageTests(unittest.TestCase):
    def _picture(self, base, name, color, size=(320, 160)):
        path = base / name
        with Image.new("RGBA", size, color) as image:
            image.save(path)
        return path

    def _registry(self, base, profiles):
        (base / "profiles.json").write_text(json.dumps({"profiles": [asdict(profile) for profile in profiles]}), encoding="utf-8")

    def test_import_copies_alpha_crop_and_survives_original_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = self._picture(base, "selected.png", (250, 0, 0, 100))
            managed = profile_images.import_profile_image(source, base)
            source.unlink()
            self.assertTrue(managed.startswith(".profile-images/"))
            with Image.open(base / managed) as image:
                self.assertEqual(image.size, (512, 512))
                pixel = image.getpixel((256, 256))
                self.assertEqual(pixel[3], 100)
                self.assertLessEqual(abs(pixel[0] - 250), 2)
            profile = BotProfile("work", "Work", "sheet", image_file=managed)
            image = profile_images.load_profile_image(profile, base, size=(80, 80))
            try:
                self.assertEqual(image.size, (80, 80))
                pixel = image.getpixel((40, 40))
                self.assertEqual(pixel[3], 100)
                self.assertLessEqual(abs(pixel[0] - 250), 2)
            finally:
                image.close()

    def test_two_profiles_never_share_fallback_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            red = profile_images.import_profile_image(self._picture(base, "red.png", "red"), base)
            blue = profile_images.import_profile_image(self._picture(base, "blue.png", "blue"), base)
            for name, selected, expected in (("first", red, (255, 0, 0, 255)), ("second", blue, (0, 0, 255, 255))):
                image = profile_images.load_profile_image(BotProfile(name, name, "sheet", image_file=selected), base)
                try:
                    self.assertEqual(image.getpixel((70, 70)), expected)
                finally:
                    image.close()
            (base / red).unlink()
            self.assertIsNone(profile_images.load_profile_image(BotProfile("first", "First", "sheet", image_file=red), base))

    def test_jpeg_exif_orientation_is_applied_before_crop(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "rotated.jpg"
            with Image.new("RGB", (80, 40), "blue") as image:
                image.paste("red", (0, 0, 40, 40))
                exif = Image.Exif()
                exif[274] = 6
                image.save(source, exif=exif)
            selected = profile_images.import_profile_image(source, base)
            with Image.open(base / selected) as image:
                top, bottom = image.getpixel((256, 80)), image.getpixel((256, 430))
                self.assertGreater(top[0], top[2])
                self.assertGreater(bottom[2], bottom[0])
                self.assertIsNone(image.getexif().get(274))

    def test_corrupt_missing_or_unsafe_selected_image_uses_logo_then_none(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            managed = ".profile-images/" + "a" * 32 + ".png"
            (base / ".profile-images").mkdir()
            (base / managed).write_bytes(b"not an image")
            self._picture(base, "logo.png", "green")
            for invalid in ("", managed, ".profile-images/" + "b" * 32 + ".png", "../outside.png", str(base / "logo.png")):
                profile = BotProfile("work", "Work", "sheet", image_file=invalid)
                image = profile_images.load_profile_image(profile, base)
                try:
                    self.assertEqual(image.getpixel((60, 60)), (0, 128, 0, 255))
                finally:
                    image.close()
            (base / "logo.png").unlink()
            self.assertIsNone(profile_images.load_profile_image(BotProfile("work", "Work", "sheet"), base))

    def test_caps_invalid_format_and_traversal_are_rejected_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = self._picture(base, "selected.png", "red")
            for constant in ("MAX_SOURCE_BYTES", "MAX_SOURCE_PIXELS"):
                with patch.object(profile_images, constant, 1), self.assertRaises(ValueError) as error:
                    profile_images.import_profile_image(source, base)
                self.assertNotIn(str(source), str(error.exception))
            invalid = base / "invalid.png"
            invalid.write_bytes(b"generated invalid bytes")
            with self.assertRaises(ValueError):
                profile_images.import_profile_image(invalid, base)
            self.assertIsNone(profile_images.managed_image_path(".profile-images/../outside.png", base))
            self.assertIsNone(profile_images.managed_image_path(".profile-images\\" + "a" * 32 + ".png", base))
            self.assertFalse((base / ".profile-images").exists())

    def test_metadata_patch_preserves_latest_fields_and_does_not_access_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = profile_images.import_profile_image(self._picture(base, "selected.png", "red"), base)
            latest = BotProfile("work", "Updated name", "updated-sheet", currency="RUB", track_money_source=True, autostart=True)
            other = BotProfile("other", "Other", "other-sheet")
            self._registry(base, [latest, other])
            with patch.object(bot_profiles, "load_token", side_effect=AssertionError("Token load forbidden")), patch.object(bot_profiles, "save_token", side_effect=AssertionError("Token save forbidden")), patch.object(bot_profiles, "get_profile_token", side_effect=AssertionError("Token lookup forbidden")):
                selected = set_profile_image("work", image, base_dir=base)
                self.assertEqual(selected, replace(latest, image_file=image))
                self.assertEqual(bot_profiles.get_profile("other", base), other)
                self.assertEqual(set_profile_image("work", "", base_dir=base), latest)
            with self.assertRaises(ValueError):
                set_profile_image("work", "../outside.png", base_dir=base)

    def test_old_registry_defaults_and_synthetic_personal_metadata_update(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = profile_images.import_profile_image(self._picture(base, "selected.png", "blue"), base)
            selected = set_profile_image("personal", image, base_dir=base)
            self.assertTrue(selected.legacy)
            self.assertEqual(selected.image_file, image)
            raw = asdict(selected)
            del raw["image_file"]
            (base / "profiles.json").write_text(json.dumps({"profiles": [raw]}), encoding="utf-8")
            self.assertEqual(bot_profiles.list_profiles(base)[0].image_file, "")
            with self.assertRaises(ValueError):
                bot_profiles._validate(replace(selected, image_file=None))


if __name__ == "__main__":
    unittest.main()
