"""
Grad-CAM explainer for imaging specialists (DenseNet201/ResNet50/
EfficientNet) — highlights which pixels drove the prediction, per the
proposal's original explainability-layer plan. Real implementation using
forward/backward hooks on the last convolutional layer; falls back to a
clearly labeled stub when torch isn't installed, same pattern as
module5-modelzoo's imaging specialists.
"""
try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except (ImportError, OSError):
    TORCH_AVAILABLE = False

from explainers.base import Explainer, Explanation


class GradCamExplainer(Explainer):
    name = "grad_cam"

    def is_available(self) -> bool:
        return TORCH_AVAILABLE

    def explain(self, specialist, case: dict, prediction) -> Explanation:
        if not TORCH_AVAILABLE:
            return Explanation(
                method=self.name,
                summary="Grad-CAM unavailable — torch/torchvision not installed in this "
                        "environment. Install them to get real pixel-level heatmaps.",
                details=None,
                is_stub=True,
            )

        backbone = getattr(specialist, "backbone", None)
        image = case.get("image")
        if backbone is None or image is None:
            return Explanation(
                method=self.name,
                summary="Grad-CAM needs an imaging specialist with a `.backbone` and a "
                        "`case['image']` tensor — skipping for this case.",
                details=None,
                is_stub=True,
            )

        # Real Grad-CAM: hook the last conv layer, run a forward+backward pass,
        # weight activations by their gradients, ReLU, upsample to input size.
        activations, gradients = {}, {}

        def forward_hook(module, inp, out):
            activations["value"] = out.detach()

        def backward_hook(module, grad_in, grad_out):
            gradients["value"] = grad_out[0].detach()

        last_conv = _find_last_conv_layer(backbone)
        h1 = last_conv.register_forward_hook(forward_hook)
        h2 = last_conv.register_full_backward_hook(backward_hook)

        try:
            backbone.zero_grad()
            image = image.clone().requires_grad_(True)
            output = backbone(image)
            pred_idx = int(torch.argmax(output, dim=1).item())
            output[0, pred_idx].backward()

            weights = gradients["value"].mean(dim=(2, 3), keepdim=True)
            cam = F.relu((weights * activations["value"]).sum(dim=1, keepdim=True))
            cam = F.interpolate(cam, size=image.shape[2:], mode="bilinear", align_corners=False)
            cam = cam.squeeze().detach()
            cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)  # normalize to [0, 1]
        finally:
            h1.remove()
            h2.remove()

        return Explanation(
            method=self.name,
            summary=f"Grad-CAM heatmap generated over {last_conv.__class__.__name__} activations "
                    f"for predicted class index {pred_idx}.",
            details=cam,  # a (H, W) tensor a dashboard would overlay on the original image
        )


def _find_last_conv_layer(model):
    """Walks a torchvision backbone to find its last Conv2d layer — the standard
    Grad-CAM target (deepest layer with meaningful spatial resolution)."""
    last_conv = None
    for module in model.modules():
        if isinstance(module, torch.nn.Conv2d):
            last_conv = module
    if last_conv is None:
        raise ValueError("No Conv2d layer found in this backbone — Grad-CAM needs a CNN.")
    return last_conv
