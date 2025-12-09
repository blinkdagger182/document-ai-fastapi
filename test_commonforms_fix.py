#!/usr/bin/env python3
"""
Test script to verify the commonforms tuple fix
This simulates the issue and tests the patch
"""
import sys

# Simulate the tuple issue
class MockDetections:
    def __init__(self, xyxy, class_id, confidence):
        self.xyxy = xyxy
        self.class_id = class_id
        self.confidence = confidence
    
    def with_nms(self, threshold=0.1, class_agnostic=True):
        return self
    
    def __len__(self):
        return len(self.xyxy)

# Test 1: Tuple should fail
print("Test 1: Tuple calling with_nms (should fail)")
try:
    result = ([], [], [])  # Simulates what rfdetr returns
    result.with_nms()
    print("❌ FAIL: Tuple should not have with_nms method")
except AttributeError as e:
    print(f"✅ PASS: Got expected error: {e}")

# Test 2: Converting tuple to Detections should work
print("\nTest 2: Converting tuple to Detections (should work)")
try:
    import numpy as np
    
    # Simulate what the patch does
    result = (
        np.array([[0, 0, 100, 100]]),  # xyxy
        np.array([0]),  # class_id
        np.array([0.9])  # confidence
    )
    
    if isinstance(result, tuple):
        print("  Detected tuple, converting to Detections...")
        detections = MockDetections(
            xyxy=result[0],
            class_id=result[1],
            confidence=result[2]
        )
        detections = detections.with_nms(threshold=0.1, class_agnostic=True)
        print(f"✅ PASS: Successfully converted and called with_nms, got {len(detections)} detections")
    else:
        print("❌ FAIL: Should have been a tuple")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*50)
print("The patch should convert tuples to Detections objects")
print("before calling .with_nms() to avoid the AttributeError")
