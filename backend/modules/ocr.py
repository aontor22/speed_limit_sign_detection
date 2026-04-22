from __future__ import annotations

import re
import cv2
import numpy as np
from typing import Optional
from pathlib import Path

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

from utils.logger import setup_logger
from utils.helpers import preprocess_for_ocr, crop_with_padding

log = setup_logger("OCR")


# ──────────────────────────────────────────────────────────────────────────────
# Valid Speed Limits (sanity filter)
# ──────────────────────────────────────────────────────────────────────────────

# Standard speed limits used internationally (km/h)
VALID_SPEED_LIMITS = {10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60,
                      65, 70, 75, 80, 90, 100, 110, 120, 130, 140}


# ──────────────────────────────────────────────────────────────────────────────
# SpeedOCR
# ──────────────────────────────────────────────────────────────────────────────

class SpeedOCR:
    """
    Extracts the numeric speed limit from a cropped sign image.

    Args:
        tesseract_config : Tesseract CLI config string
        min_confidence   : Minimum Tesseract word-level confidence (0–100)
        upscale_factor   : How much to enlarge the crop before OCR
        padding          : Extra pixels added around the bounding box crop
        preprocess       : Whether to apply image preprocessing pipeline
        tesseract_cmd    : Custom path to tesseract binary (optional)
    """

    # Default Tesseract config:
    #   --psm 6  → uniform block of text
    #   --oem 3  → LSTM engine
    #   whitelist → only digits (eliminates 'O' vs '0' confusion, etc.)
    DEFAULT_CONFIG = "--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789"

    def __init__(self,
                 tesseract_config: str = DEFAULT_CONFIG,
                 min_confidence: int = 40,
                 upscale_factor: float = 2.5,
                 padding: int = 10,
                 preprocess: bool = True,
                 tesseract_cmd: Optional[str] = None):

        if not HAS_TESSERACT:
            log.error("pytesseract or Pillow not installed. OCR disabled.")

        self.config = tesseract_config
        self.min_conf = min_confidence
        self.upscale = upscale_factor
        self.padding = padding
        self.preprocess = preprocess

        # Override tesseract binary path if specified
        if tesseract_cmd and HAS_TESSERACT:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            log.info(f"Tesseract binary path set to: {tesseract_cmd}")

        self._verify_tesseract()

    # ── Public API ────────────────────────────────────────────────────────────

    def extract_speed(self,
                      frame: np.ndarray,
                      x1: int, y1: int, x2: int, y2: int
                      ) -> tuple[Optional[int], str, float]:
        """
        Extract the speed limit number from a detected sign bounding box.

        Args:
            frame     : Full BGR frame
            x1,y1,x2,y2 : Bounding box of the detected sign

        Returns:
            Tuple of (speed_int_or_None, raw_ocr_string, ocr_confidence)

            - speed_int_or_None : Parsed integer speed limit, or None if
                                  OCR failed / result out of valid range
            - raw_ocr_string    : Raw text returned by Tesseract
            - ocr_confidence    : Mean word confidence from Tesseract (0–100)
        """
        if not HAS_TESSERACT:
            return None, "", 0.0

        # Step 1: Crop the sign region
        crop = crop_with_padding(frame, x1, y1, x2, y2, self.padding)
        if crop is None or crop.size == 0:
            log.debug("Empty crop — skipping OCR")
            return None, "", 0.0

        # Step 2: Pre-process for OCR
        processed = preprocess_for_ocr(crop, self.upscale) if self.preprocess else crop

        # Step 3: Run Tesseract
        raw_text, confidence = self._run_tesseract(processed)

        # Step 4: Post-process / validate
        speed = self._parse_speed(raw_text)

        log.debug(f"OCR raw='{raw_text}' conf={confidence:.1f} → speed={speed}")
        return speed, raw_text, confidence

    def extract_speed_from_crop(self, crop: np.ndarray
                                ) -> tuple[Optional[int], str, float]:
        """
        Convenience method — accepts a pre-cropped image directly.

        Args:
            crop: BGR numpy array of the sign region

        Returns:
            Same as extract_speed().
        """
        if not HAS_TESSERACT or crop is None or crop.size == 0:
            return None, "", 0.0

        processed = preprocess_for_ocr(crop, self.upscale) if self.preprocess else crop
        raw_text, confidence = self._run_tesseract(processed)
        speed = self._parse_speed(raw_text)
        return speed, raw_text, confidence

    # ── Private ───────────────────────────────────────────────────────────────

    def _run_tesseract(self, image: np.ndarray) -> tuple[str, float]:
        """
        Call pytesseract on a preprocessed image.

        Returns:
            (raw_text, mean_confidence)
        """
        try:
            # Use data output for confidence scores
            data = pytesseract.image_to_data(
                Image.fromarray(image),
                config=self.config,
                output_type=pytesseract.Output.DICT,
            )

            # Filter by minimum confidence
            texts, confs = [], []
            for i, conf in enumerate(data["conf"]):
                if int(conf) >= self.min_conf:
                    word = data["text"][i].strip()
                    if word:
                        texts.append(word)
                        confs.append(int(conf))

            raw = " ".join(texts).strip()
            mean_conf = sum(confs) / len(confs) if confs else 0.0
            return raw, mean_conf

        except Exception as e:
            log.debug(f"Tesseract error: {e}")
            return "", 0.0

    @staticmethod
    def _parse_speed(raw_text: str) -> Optional[int]:
        """
        Extract a valid speed limit integer from raw OCR text.

        Rules:
          - Extract all digit sequences
          - Pick the first sequence that is 2–3 digits long
          - Validate against known speed limits
          - If exact match fails, find nearest valid limit within ±5 km/h
            (accounts for OCR off-by-one errors on individual digits)
        """
        if not raw_text:
            return None

        # Find all digit sequences
        numbers = re.findall(r"\d+", raw_text.replace(" ", ""))
        for num_str in numbers:
            if len(num_str) < 2 or len(num_str) > 3:
                continue
            try:
                value = int(num_str)
            except ValueError:
                continue

            # Exact match in valid speeds
            if value in VALID_SPEED_LIMITS:
                return value

            # Fuzzy match: within ±5 of a valid limit
            for valid in sorted(VALID_SPEED_LIMITS):
                if abs(value - valid) <= 5:
                    return valid

        return None   # Could not extract a valid speed

    def _verify_tesseract(self) -> None:
        """Check that Tesseract is installed and reachable."""
        if not HAS_TESSERACT:
            return
        try:
            version = pytesseract.get_tesseract_version()
            log.info(f"Tesseract OCR version: {version}")
        except Exception as e:
            log.warning(
                f"Tesseract not found or not accessible: {e}\n"
                "Install instructions:\n"
                "  Ubuntu/Debian : sudo apt install tesseract-ocr\n"
                "  Windows       : https://github.com/UB-Mannheim/tesseract/wiki\n"
                "  macOS         : brew install tesseract"
            )
