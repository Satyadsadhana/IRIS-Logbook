import torch
import sys

print("PyTorch Version:", torch.__version__)
try:
    model = torch.load('model/best_face.pth', map_location='cpu')
    print("Successfully loaded model")
except Exception as e:
    print("Failed to load model.")
    print("Error type:", type(e))
    print("Error message:", str(e))
