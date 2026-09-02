# Foundation-model wiring status (RadFM / BiomedParse / SegVol / OmiCLIP / MeDiM / Mamba-Health / MICViT)

Requested: wire in the six SOTA models named in the routing spec
(MeDiM/RadFM, BiomedParse/SegVol, TabPFN, OmiCLIP, Mamba-Health, MICViT)
for real. TabPFN was already real in this repo (`tabular_vitals_tabpfn.py`)
before this pass. Status of the other five:

## Real, code added this pass (`module5-modelzoo/models/foundation_*.py`)

| Model | Repo | What's actually wired |
|---|---|---|
| **RadFM** | [chaoyi-wu/RadFM](https://github.com/chaoyi-wu/RadFM) | Real loading path (`MultiLLaMAForCausalLM` from the repo's own `Model/RadFM/multimodality_model.py`, confirmed from their README) + `is_available()`/registry wiring. `predict()` deliberately left `NotImplementedError` — see below. |
| **BiomedParse** | [microsoft/BiomedParse](https://github.com/microsoft/BiomedParse) | Real loading + `predict()`, copied from BiomedParse's own published quick-start snippet (`BaseModel`/`build_model`/`load_opt_from_config_files`/`init_distributed` chain verified; the exact import path for `interactive_infer_image` is inferred, not verified — flagged in the file). |
| **SegVol** | [BAAI-DCAI/SegVol](https://github.com/BAAI-DCAI/SegVol) (via `transformers`) | Real loading, copied verbatim from the model card's `AutoModel.from_pretrained("BAAI/SegVol", trust_remote_code=True)` example. `predict()`'s exact inference method name is inferred from the same example, which stops before showing it — flagged in the file. |
| **OmiCLIP** | ships inside [GuangyuWangLab2021/Loki](https://github.com/GuangyuWangLab2021/Loki) | Confirmed real and its weight location confirmed, but I could not verify a real loading/inference code snippet the way I could for the other three. Left as an honest stub with `NotImplementedError` rather than fabricating an import path — see the file's docstring for exactly what's needed to finish it. |

**All four auto-degrade to `StubSpecialistModel`** through `registry.py`'s
existing try/except pattern — confirmed by re-running `module5-modelzoo/demo.py`
after wiring them in: all four new modalities (`radiology_vqa`,
`prompted_segmentation`, `ct_volumetric`, `pathology_omics`) appear in the
registry, all report `real: False`, and the rest of the demo (vitals,
existing imaging, fusion) runs exactly as before.

### Why none of these actually run here, even with the code written

- **No GPU.** RadFM's own README: *"never try to perform this in cpu and
  gpus are all you need."* Same practical requirement for the others.
- **No Hugging Face access.** This sandbox's network allowlist covers
  `github.com`/`pypi.org`/etc., not `huggingface.co` — and every one of
  these four ships its weights there (BiomedParse, SegVol, OmiCLIP/Loki)
  or off Baidu (RadFM).
- **Two of the four aren't pip packages** (RadFM, BiomedParse) — they're
  cloned repos with local-path imports, which is why the code above reads
  from an env-var-configured `FEDHEAL_*_REPO_PATH` rather than a normal
  `pip install`.

This mirrors exactly how `imaging_chest_xray.py` etc. already handle
torch/torchvision not being installed here — real code, correctly
written, honestly marked untested-in-this-sandbox.

## RadFM's `predict()`: interface mismatch, not a TODO to just fill in

RadFM is a generative vision-language model — its own usage example is a
free-text Q&A ("Can you identify any visible signs of Cardiomegaly in the
image?" → "yes"), not a fixed-class classifier like every other specialist
in this zoo. Forcing that into `PredictionResult(label, confidence)`
without a real checkpoint to validate against would mean fabricating what
a "confidence" even means for a generated sentence — exactly the kind of
invented-precision-metric this project's Module 8 review explicitly
avoids. `predict()` raises `NotImplementedError` with a pointer to the
real generation entry point (`my_embedding_layer.py` +
`multimodality_model.py`) so whoever picks this up on a GPU machine with a
real checkpoint writes it against the actual API, not a guess.

## Not available to wire in at all

**MeDiM** — real paper (Mao et al., UCSC-VLAA, ICLR 2026 submission), real
GitHub repo (`UCSC-VLAA/MeDiM`), but the repo's own status as of this
check: *"Code... will be available soon... still under development."*
There is no runnable implementation published yet — this isn't a gap in
this codebase, it's upstream not having shipped code. Nothing to wire in
until they release it.

## Unresolved — need your input before I write anything

**Mamba-Health** and **MICViT** don't resolve to any public model I could
find under those exact names. There's a large published ecosystem of
Mamba-based medical models (nnMamba, SegMamba, VM-UNet, CMViM — a real
"Contrastive Masked Vim Autoencoder" for 3D multimodal AD classification —
and others), and plenty of medical vision-transformer fusion work, but
nothing matching "Mamba-Health" or "MICViT" specifically turned up.

Before I scaffold specialists for these two, I'd want to know: do you have
a specific paper/repo in mind for either (maybe an internal/private one, or
one I'm just not finding), or should these two be swapped for a real
published model that fits the same routing role (sequential/signal data
for Mamba-Health; general cross-modal fusion for MICViT)? Writing
integration code against a name with no real implementation behind it
would mean inventing an API — same failure mode as everything else this
doc is trying to avoid.

## Modernization pass: BiomedCLIP / nnU-Net / Evo 2 / UNI2-h

A separate pass from the six models above — this one implements
`docs/model-algorithm-catalog.md`'s upgrade recommendations for the
*existing* legacy imaging/segmentation/histopathology specialists, plus
one genuinely new specialist (Evo 2), rather than wiring in more
originally-requested SOTA models. Same standard applied throughout: real,
verified loading snippets from each model's own documentation, honestly
marked untested where this sandbox can't run them, no fabricated APIs.

| Model | Repo / model card | Upgrades | What's actually wired |
|---|---|---|---|
| **BiomedCLIP** | [microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224](https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224) (via `open_clip`) | `DenseNet201ChestXrayModel`, `ResNet50RetinaModel`, `EfficientNetSkinLesionModel` | Real loading (`open_clip.create_model_from_pretrained("hf-hub:microsoft/BiomedCLIP-...")`, copied from the model card's own quick-start) + a real, from-scratch-trainable `Conv1d`-based fine-tuned head (the "CNN+ViT hybrid" the project's instructions asked for) operating on `encode_image()`'s documented pooled output — see `module5-modelzoo/models/foundation_biomedclip.py` |
| **nnU-Net (v2)** | [MIC-DKFZ/nnUNet](https://github.com/MIC-DKFZ/nnUNet), pip `nnunetv2` | `UNetSegmentationModel` | Real loading via `nnunetv2.inference.predict_from_raw_data.nnUNetPredictor`, copied from the package's own documented inference API. Genuinely different from the other rows here: nnU-Net is a *training framework*, not a downloadable pretrained checkpoint — there's no default weights to ship, `FEDHEAL_NNUNET_MODEL_FOLDER` must point at a model folder a hospital already trained on its own labeled data. See `module5-modelzoo/models/foundation_nnunet.py` |
| **UNI2-h** (patch encoder) | [MahmoodLab/UNI2-h](https://huggingface.co/MahmoodLab/UNI2-h) (via `timm`) | `HistopathologyMILModel` (module6) | Real loading (`timm.create_model("hf-hub:MahmoodLab/UNI2-h", pretrained=True, ...)`, copied from the model card), feeding a real CLAM-style *gated*-attention MIL head (an upgrade from the legacy model's plain softmax attention). Virchow2/Prov-GigaPath are equivalent-tier, same-shape alternatives, selectable via `FEDHEAL_PATHOLOGY_ENCODER_HUB_ID` if one of those is already HF-authorized for a given deployment instead. See `module6-condition-router/models/foundation_pathology_mil.py` |
| **Evo 2** | [ArcInstitute/evo2](https://github.com/ArcInstitute/evo2), pip `evo2` | *(new — no legacy predecessor; fills the catalog's "still missing entirely" genomic-variant row)* | Real loading (`Evo2("evo2_7b")` + `score_sequences()`, copied from the repo's own quick-start) implementing the zero-shot variant-effect log-likelihood-ratio method from Evo 2's own paper. See `module5-modelzoo/models/foundation_evo2.py` |

**All four auto-degrade** through the same `registry.py` /
`condition_registry_builder.py` try/except pattern as the six models
above — re-running both `module5-modelzoo/demo.py` and
`module6-condition-router/demo.py` after wiring them in confirms: the new
`genomic_variant` modality appears in module5's registry (`real: False`
here), the two new `genomic_variant_breast_cancer`/`genomic_variant_
leukemia` specialist_ids fire in module6's breast-cancer/leukemia demo
output as labeled stubs, `histopathology_breast_cancer` still resolves
(to the legacy `HistopathologyMILModel` stub, since UNI2-h isn't
available here either), and every pre-existing modality/condition
continues to behave exactly as before.

### Why none of these four actually run here either

Same three blockers as the six models above, plus one new one specific to
nnU-Net:

- **No GPU** — all four either need one outright (Evo 2, UNI2-h at
  practical whole-slide scale) or strongly recommend one (BiomedCLIP,
  nnU-Net).
- **No Hugging Face access** — BiomedCLIP, UNI2-h, and Evo 2 all ship
  weights on the HF Hub; UNI2-h's specifically is *gated* (requires
  accepting MahmoodLab's terms + an authenticated `HF_TOKEN`), a step
  beyond the plain network-access blocker the other models hit.
- **nnU-Net has no default weights at all, by design** — it's a
  self-configuring training framework, not a pretrained checkpoint. Even
  with a GPU and full network access, `NNUNetSegmentationModel` correctly
  raises until `FEDHEAL_NNUNET_MODEL_FOLDER` points at a model a hospital
  has actually trained on its own labeled CT data — there's no honest way
  to ship a generic pretrained nnU-Net the way the other three ship a
  generic pretrained checkpoint.

Real code, correctly written against each project's own documented API,
honestly marked untested-in-this-sandbox — the same standard as every
other entry in this file.
