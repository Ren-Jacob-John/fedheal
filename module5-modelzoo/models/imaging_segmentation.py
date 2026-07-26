"""
Segmentation specialist — U-Net, per the proposal ("U-Net for pixel-level
segmentation rather than classification, e.g. outlining a tumor's
boundary"). torchvision doesn't ship a U-Net, so this is a small, standard
U-Net implemented directly — the classic encoder-decoder-with-skip-
connections architecture (Ronneberger et al. 2015), not a pretrained model.

Same torch/torchvision dependency note as the other imaging specialists —
see imaging_chest_xray.py's docstring.

Unlike the classification specialists, this one's predict() returns a
per-pixel mask as raw_output instead of a single label/confidence pair —
task="segmentation" is the router/fusion layer's signal to treat the
output differently (see fusion.py).
"""
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except (ImportError, OSError):
    TORCH_AVAILABLE = False

from base import PredictionResult, SpecialistModel


if TORCH_AVAILABLE:
    class _DoubleConv(nn.Module):
        def __init__(self, in_ch, out_ch):
            super().__init__()
            self.block = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1), nn.BatchNorm2d(out_ch), nn.ReLU(inplace=True),
            )

        def forward(self, x):
            return self.block(x)


    class SimpleUNet(nn.Module):
        """A small U-Net: 3 downsampling stages, bottleneck, 3 upsampling stages."""

        def __init__(self, in_channels=1, out_channels=1, base_filters=32):
            super().__init__()
            f = base_filters
            self.down1 = _DoubleConv(in_channels, f)
            self.down2 = _DoubleConv(f, f * 2)
            self.down3 = _DoubleConv(f * 2, f * 4)
            self.bottleneck = _DoubleConv(f * 4, f * 8)
            self.pool = nn.MaxPool2d(2)

            self.up3 = nn.ConvTranspose2d(f * 8, f * 4, 2, stride=2)
            self.dec3 = _DoubleConv(f * 8, f * 4)
            self.up2 = nn.ConvTranspose2d(f * 4, f * 2, 2, stride=2)
            self.dec2 = _DoubleConv(f * 4, f * 2)
            self.up1 = nn.ConvTranspose2d(f * 2, f, 2, stride=2)
            self.dec1 = _DoubleConv(f * 2, f)

            self.out_conv = nn.Conv2d(f, out_channels, 1)

        def forward(self, x):
            d1 = self.down1(x)
            d2 = self.down2(self.pool(d1))
            d3 = self.down3(self.pool(d2))
            bottleneck = self.bottleneck(self.pool(d3))

            u3 = self.up3(bottleneck)
            u3 = self.dec3(torch.cat([u3, d3], dim=1))
            u2 = self.up2(u3)
            u2 = self.dec2(torch.cat([u2, d2], dim=1))
            u1 = self.up1(u2)
            u1 = self.dec1(torch.cat([u1, d1], dim=1))

            return self.out_conv(u1)  # logits, same H/W as input


class UNetSegmentationModel(SpecialistModel):
    name = "unet-segmentation-v1"
    modality = "ct_scan"   # also applies to MRI slices — swap per hospital's imaging type
    task = "segmentation"

    def __init__(self, in_channels: int = 1):
        if not TORCH_AVAILABLE:
            raise ImportError(
                f"{self.name} needs torch. See this module's requirements.txt."
            )
        self.net = SimpleUNet(in_channels=in_channels, out_channels=1)
        self.net.eval()

    def is_available(self) -> bool:
        return TORCH_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        # case["image"] expected as (1, C, H, W), already normalized upstream.
        image = case["image"]
        with torch.no_grad():
            logits = self.net(image)
            mask = (torch.sigmoid(logits) > 0.5).float()
            coverage = float(mask.mean().item())  # fraction of pixels flagged — a coarse severity proxy

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label="region_flagged" if coverage > 0.01 else "no_region_flagged",
            confidence=coverage,       # not a class probability — fraction of image flagged
            raw_output=mask,           # the actual per-pixel mask a clinician would overlay
        )
