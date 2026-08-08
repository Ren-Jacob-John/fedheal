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
