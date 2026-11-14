"""After local retraining, regenerate lightweight cloud-serving weights."""
from pathlib import Path
import numpy as np
import torch
from ticketpilot.model import ROOT

def export_weights():
    states = torch.load(ROOT / "artifacts" / "model.pt", map_location="cpu", weights_only=True)
    out = ROOT / "artifacts" / "model_numpy.npz"
    np.savez_compressed(out,
        w1=states["net.0.weight"].cpu().numpy(), b1=states["net.0.bias"].cpu().numpy(),
        w2=states["net.3.weight"].cpu().numpy(), b2=states["net.3.bias"].cpu().numpy())
    print(f"Exported {out}")

if __name__ == "__main__":
    export_weights()
