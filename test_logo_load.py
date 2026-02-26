#!/usr/bin/env python3
"""Test logo loading without running full DPG app."""
import os
import sys
from PIL import Image
import numpy as np

logo_path = os.path.join(os.path.dirname(__file__), "logo.ico")
print(f"Logo path: {logo_path}")
print(f"Logo exists: {os.path.exists(logo_path)}")

if os.path.exists(logo_path):
    try:
        img = Image.open(logo_path).convert("RGBA")
        print(f"Original size: {img.size}")
        
        img_resized = img.resize((50, 50), Image.Resampling.LANCZOS)
        print(f"Resized to: {img_resized.size}")
        
        img_array = np.array(img_resized) / 255.0
        print(f"Array shape: {img_array.shape}")
        print(f"Array dtype: {img_array.dtype}")
        print(f"Array min/max: {img_array.min():.3f}/{img_array.max():.3f}")
        
        print("\n✓ Logo loaded successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error loading logo: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
else:
    print("\n✗ Logo file not found!")
    sys.exit(1)
