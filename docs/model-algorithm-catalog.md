# FedHeal — Model / Algorithm / Framework Catalog

**Last modernized:** this revision replaces the original 2020–2023-era
catalog with the current (2025–2026) generation of models per modality.
The old catalog wasn't wrong, it's just aged — most fields below have
since gained **foundation models**: large models pretrained once on huge
unlabeled/weakly-labeled corpora, then adapted cheaply per task instead of
training a CNN/tree from scratch per hospital.

**Purpose of this document:** every future stage/week of development pulls
its model choices from (or explicitly extends) this list. It's not limited
to what's already implemented in `module5-modelzoo` — that module now has
9 specialist entries spanning several generations (XGBoost, TabPFN v2,
DenseNet201, ResNet50, EfficientNet, U-Net, plus RadFM/BiomedParse/
SegVol/OmiCLIP added most recently — see
`docs/foundation-models-status.md` for which of those actually run vs.
are real-but-unavailable-here vs. blocked upstream). This document is the
full menu, current generation.

Two things every disease-specific pipeline needs, per the project's own
framing ("a prediction a doctor can check, not a black box"):
1. **A solution model** — something that outputs a diagnosis/risk/finding.
2. **A reasoning/explainability method** — something that shows *why*.

**A federation-specific caveat that applies throughout this document:**
foundation models are typically hundreds of millions to billions of
parameters. A hospital cannot realistically fine-tune all of one locally
every round the way it can retrain a small CNN or XGBoost tree. The
practical pattern used across every section below is:
**freeze the foundation model → run it once per case as a feature
extractor → federate only a small classifier/regression head on top of
its embeddings.** That keeps FedAvg fast and keeps raw data local, while
still getting foundation-model-quality representations. Where that's not
the pattern, it's called out explicitly.

---

## 1. Imaging — classification (2D: X-ray, retina, skin, mammogram, etc.)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **BiomedCLIP** | **Current** | Vision-language foundation model, contrastive-pretrained on ~15M biomedical image-text pairs from PubMed Central; produces embeddings usable zero-shot or with a lightweight fine-tuned head | General biomedical image classification across modalities, good default starting point |
| **RadFM** | **Current, but generative not classification** | Radiology-specific vision-language model (Wu et al., MedMD dataset) — answers free-text clinical questions about a scan rather than outputting a fixed-class label; see `module5-modelzoo/models/foundation_radfm.py` for the interface-mismatch this creates against this zoo's label+confidence contract | When free-text radiologic Q&A/reasoning is the actual need, not a classification score |
| **CheXzero** | **Current** | Contrastive pretraining directly on MIMIC-CXR image-report pairs; demonstrated radiologist-level zero-shot multi-label chest pathology classification without explicit annotations | Chest X-ray, when labeled data per hospital is scarce |
| **CXRBase** | **Current** | Masked-autoencoder self-supervised foundation model trained on 1M+ unlabeled CXR images, then fine-tuned for disease classification/localization | Chest X-ray, when you have volume of *unlabeled* local images plus a smaller labeled set |
| **MedGemma** | **Current** | Google's open-weight multimodal medical foundation model (image + text); can be self-hosted, which matters for a hospital-local deployment | General-purpose medical image reasoning + generating the "why" narrative in one model |
| ResNet50 / DenseNet201 / EfficientNet (ImageNet-pretrained) | **Legacy — still usable as a baseline, not SOTA** | This is what's currently in `module5-modelzoo`. Fine as a fast, cheap, well-understood fallback; foundation-model embeddings now consistently outperform ImageNet transfer learning on medical images specifically, since ImageNet's photos are a poor match for medical image statistics | Keep as the "torch not installed / low-resource hospital" fallback tier, not the primary path |
| ViT / Swin Transformer / ConvNeXt | **Legacy backbone, still fine when foundation-model-pretrained** | The architecture itself isn't obsolete — it's *what it was pretrained on* that matters now. A Swin/ViT backbone pretrained via a medical foundation-model recipe (e.g. the ones above) is current; the same architecture pretrained only on ImageNet is not | Use as the underlying architecture *inside* a foundation model, not standalone |
| MobileNet / SqueezeNet | **Still current for its niche** | Nothing newer displaces these for genuinely constrained edge hardware | On-device/edge deployment at a low-resource hospital site |
| Inception v3/v4, VGG16/19, Capsule Networks | **Outdated — remove** | Superseded on essentially every benchmark by the above; keep only if a specific published baseline comparison requires them | — |

## 2. Imaging — segmentation (tumor/organ boundaries, lesion outlines)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **SAM2 / MedSAM2** | **Current** | Meta's Segment Anything Model 2, fine-tuned for medical volumes; treats a 3D scan as a "video" and propagates a single prompt through the volume — dramatically fewer labels needed than U-Net-family training | Volumetric CT/MRI segmentation with limited per-hospital labeled masks; interactive clinician-in-the-loop correction |
| **BiomedParse** | **Current** | Joint segmentation/detection/recognition across 9 imaging modalities via text prompts (Microsoft) — one model instead of one-per-modality; see `module5-modelzoo/models/foundation_biomedparse.py` for real (untested-here) integration code | Text-prompted segmentation across modalities without training a separate model per one |
| **SegVol** | **Current** | Volumetric CT segmentation via point/box/text prompts, 200+ anatomical categories (BAAI); ships as a standard `transformers` `trust_remote_code` model — see `module5-modelzoo/models/foundation_segvol.py` | CT-specific volumetric segmentation, broader anatomical category coverage than a custom-trained U-Net |
| **nnU-Net** | **Current — still the gold-standard baseline** | Not obsolete: 2026 papers keep finding it competitive with or beating out-of-the-box SAM2 on task-specific, well-labeled datasets. Self-configuring — picks its own architecture/preprocessing per dataset | Default when a hospital has a reasonably sized labeled segmentation dataset for one specific task |
| Attention U-Net, V-Net, U-Net++ | **Legacy — nnU-Net supersedes these as a default choice** | Individually still published/used, but nnU-Net's auto-configuration generally reaches the same or better results with less manual tuning | Keep only for specific architectures a paper you're replicating requires |
| Mask R-CNN, DeepLab v3/v3+ | **Outdated for medical segmentation specifically** | Still fine for general computer vision; medical segmentation work has moved to the nnU-Net/SAM2 axis | — |
| Vanilla U-Net (custom, currently in zoo) | **Legacy — matches your current `imaging_segmentation.py`** | Reasonable teaching/baseline implementation; swap for nnU-Net or MedSAM2 for a real accuracy jump | Keep as the no-dependency fallback tier |

## 3. Whole-slide / histopathology imaging (breast cancer, leukemia blood smears)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **UNI (v2)** | **Current** | Pathology foundation model, self-supervised on 200M+ image patches from 350K+ whole-slide images (Mass General Brigham) | General-purpose histopathology feature extraction, any tissue type |
| **Virchow2** | **Current** | Trained on 3.1M whole-slide images (Memorial Sloan Kettering); one of the largest pathology foundation models published | Same use cases as UNI; strong alternative/ensemble partner |
| **Prov-GigaPath** | **Current** | Trained on 1.3B patches from 171K+ slides (Providence health system) | Same tier as UNI/Virchow2 |
| **CONCH** | **Current** | Vision-*language* pathology foundation model (image-caption pairs from PubMed) — lets you query slide regions with text, not just classify | When you want text-grounded reasoning over a slide, not just a label |
| **OmiCLIP** | **Current, integration unverified** | Visual-omics foundation model bridging histopathology images with spatial transcriptomics (Chen et al., Nat Methods 2025) — ships inside the `Loki` repo rather than as a standalone package; confirmed real but a verified loading/inference API couldn't be confirmed — see `module5-modelzoo/models/foundation_omiclip.py` and `docs/foundation-models-status.md` before building on this one | Correlating histopathology morphology with gene-expression-level findings, once its real API is confirmed |
| Multiple Instance Learning (MIL/CLAM) on **foundation-model embeddings** | **Current pattern** | This is how you actually use the four models above in a diagnostic pipeline: extract patch embeddings with UNI/Virchow2/Prov-GigaPath, then train a small MIL aggregator (CLAM-style) on top — that MIL head is what federates cheaply | Breast cancer histopathology (BACH, CAMELYON), any whole-slide diagnosis |
| MIL/CLAM on raw patch-CNN features | **Legacy** | Same architecture, weaker feature extractor underneath; foundation-model embeddings measurably outperform ImageNet-CNN patch features on pathology benchmarks | Fallback only if none of the above foundation models are accessible |
| HoVer-Net, Cellpose, StarDist | **Still current for their specific niche** | Nucleus/cell segmentation hasn't been fully subsumed by the slide-level foundation models above — those work at the tile/embedding level, not per-cell | Blood smear cell counting/morphology (leukemia), nucleus-level analysis |
| Graph Neural Networks on cell graphs | **Still current, complementary** | Still the right tool for explicit spatial/relational reasoning between cells, independent of the foundation-model shift above | Tumor microenvironment / cell-interaction reasoning |

## 4. Structured / tabular data (vitals, labs, EHR structured fields)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **TabPFN v2 / v2.5** | **Current** | Transformer-based tabular *foundation* model — pretrained once on synthetic tasks, then does in-context learning: no per-hospital training loop needed, just feed the local table at inference time. v2.5 handles up to ~100K rows and ~2,000 features, which fits a hospital's vitals dataset comfortably. On small-to-medium clinical tabular data, it now matches or beats tuned XGBoost | Small-to-medium tabular clinical cohorts — exactly FedHeal's structured-vitals track; also strong on missing-data imputation |
| XGBoost / LightGBM / CatBoost | **Still current, not obsolete** | Gradient-boosted trees remain the state of practice at larger scale and are what most production clinical tabular systems still run; the shift is that they're no longer the *only* strong option | Larger tabular datasets, or as an ensemble partner alongside TabPFN |
| **TabICL v2** | **Current, complementary to TabPFN** | Another 2026 tabular foundation model, optimized for scaling to larger row counts than TabPFN handles well | If a hospital's vitals table grows past TabPFN's practical row/feature ceiling |
| Random Forest, Logistic Regression / SGDClassifier | **Still current as interpretable baselines** | Not "outdated" — these remain the right choice specifically *because* they're simple to explain and federation-friendly (this is what `module3-fedlearning` already uses, correctly) | Baselines, and anywhere explainability-by-construction matters more than squeezing out extra accuracy |
| TabNet, Support Vector Machine | **Legacy** | Both superseded in head-to-head benchmarks by tabular foundation models on the datasets they were designed for | Keep only if a specific paper/benchmark you're replicating requires them |
| Multi-Layer Perceptron (MLP) baseline | **Legacy** | TabPFN/TabICL now dominate the "neural net on tabular data" niche this used to fill | — |

## 5. Genomic / omics data (leukemia subtyping, breast cancer BRCA risk)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **Evo 2** | **Current** | DNA foundation model (Arc Institute/NVIDIA, *Nature* 2026), trained on 9 trillion base pairs across all domains of life with a 1M-token context at single-nucleotide resolution — predicts functional impact of variants, including noncoding pathogenic mutations and clinically significant BRCA1 mutations, without task-specific fine-tuning | BRCA1/2 variant-effect prediction, noncoding variant interpretation — directly relevant to your breast-cancer disease track |
| **AlphaGenome** | **Current** | DeepMind model, leads (alongside Evo 2) specifically on noncoding and splice variant-effect prediction | Splice-site and regulatory-region variant interpretation |
| **AlphaMissense** | **Current** | The specialist leader for coding single-nucleotide-variant pathogenicity classification | Missense mutation pathogenicity scoring |
| **AlphaFold3** | **Current** | Predicts near-complete biomolecular systems (protein–protein, protein–drug interactions) via a diffusion architecture — this is *mechanism*, not just variant calling: shows *how* a mutation disrupts protein function | Explaining the structural "why" behind a genomic finding, drug-target discovery |
| Random Forest / SVM on gene-expression panels | **Still viable for small-N cohorts** | Genomic foundation models above need real compute and aren't yet the easy/cheap option for a small leukemia subtype cohort; classic approaches remain competitive there and are far cheaper to run | Small-N leukemia subtype classification from expression panels, when compute is constrained |
| Autoencoders / VAEs for dimensionality reduction | **Legacy pattern, mostly superseded** | Foundation model embeddings (from the models above) now typically serve the same "compress high-dim omics data" role, with better downstream performance | Keep only where no foundation model embedding is accessible for that omics type |
| Graph Neural Networks on gene/protein interaction networks | **Still current, complementary** | Independent of the foundation-model shift — still the right tool for explicit pathway-level reasoning | Explaining *why* a mutation matters at the pathway level, alongside AlphaFold3's structural view |

## 6. Clinical text / NLP (doctor's notes, radiology reports, discharge summaries)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **MedGemma** | **Current** | Google's open-weight clinical multimodal foundation model — self-hostable, which is what makes it usable inside a hospital-local, privacy-preserving deployment like FedHeal (no data leaves the building to hit an API) | Report summarization, extracting structured findings, generating the clinician-facing "reasoning" narrative |
| **Med-PaLM 2 / AMIE** | **Current, but research-tier** | Strong published benchmarks; still no FDA clearance and no confirmed general hospital deployment as of this writing — treat as a research reference point, not a production dependency | Benchmarking against, not necessarily building on directly (API-only, not self-hostable) |
| Reasoning-model-assisted diagnosis (e.g. an o3-class model doing structured differential reasoning over a case) | **Emerging/current** | A 2026 *NEJM AI* study used this pattern on unsolved rare-disease genomic cases as a diagnostic aid, not a standalone tool | Rare/undiagnosed-disease differential generation, paired with clinician review |
| ClinicalBERT, BioBERT, BlueBERT | **Legacy — still functional, not the current default** | These BERT-era encoders still work for entity extraction, but generative clinical LLMs (MedGemma and open alternatives) now generally subsume their use cases while also producing the natural-language "reasoning" the project needs — a pure encoder can't generate that narrative | Keep specifically for lightweight NER where you don't need any generation, and compute is very constrained |
| spaCy sci/med models, MedCAT | **Still current for their niche** | Fast, cheap, no GPU needed — nothing has displaced these for pure structured-field extraction at scale | Turning free text into structured fields for Module 2's validation layer |

## 7. Time-series / sequential EHR data

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| **TabPFN (as a time-series tool)** | **Current, notable 2025/2026 finding** | Recent work found the tabular foundation model TabPFN, applied to simple time-series features, outperforms specialized time-series forecasting models on several benchmarks — a genuinely surprising, current result worth knowing | Vitals-over-time forecasting, when you'd otherwise reach for a dedicated time-series model |
| Transformer EHR models (BEHRT, Med-BERT) | **Still current** | Attention-over-visit-history models haven't been displaced, just joined by the tabular-foundation-model option above | Predicting future risk from a patient's full visit/event history |
| LSTM / GRU, Temporal Convolutional Networks | **Legacy** | Transformer-based sequence models (above) now generally outperform these on EHR event-sequence tasks | Keep only as a lightweight fallback with no GPU/transformer library available |

## 8. Survival analysis (time-to-event: relapse, progression, mortality)

| Model family | Status | Notes | Good fit for |
|---|---|---|---|
| Cox Proportional Hazards | **Still current** | Genuinely not outdated — remains the standard baseline in clinical survival literature, precisely because it's interpretable and well-understood by clinicians/regulators | Baseline survival/prognosis modeling |
| Random Survival Forest, DeepSurv | **Still current** | No major foundation-model shift has displaced this field yet the way imaging/genomics/tabular have | More complex prognosis modeling than Cox alone |
| Kaplan-Meier estimation | **Still current** | Descriptive, not predictive — still the standard reporting companion to any of the above | Baseline/reporting alongside any survival model |

*(This section is the one place in the catalog with no "outdated → replace" entries — survival analysis hasn't had the same foundation-model disruption as imaging/genomics/tabular yet.)*

## 9. Multi-modal fusion (imaging + tabular + genomic + text, one patient)

| Approach | Status | Notes |
|---|---|---|
| **Native multimodal foundation models (MedGemma, CONCH)** | **Current** | These fuse modalities *by design* inside one model rather than combining separately-trained specialists after the fact — the current state of the art for multi-modal medical AI |
| **MeDiM** | **Published, not yet released** | Medical discrete diffusion model unifying image/report generation across modalities without modality-specific components (Mao et al., UCSC-VLAA, ICLR 2026 submission) — real paper, real GitHub repo, but the repo's own status is "code will be available soon." Nothing to integrate against yet; check back before building on this one |
| Attention-based cross-modal fusion (custom transformer combining separate encoders) | **Current, when you need custom modality combinations** | Still the right DIY approach when no single foundation model covers your exact combination of modalities |
| Late fusion (your current `fusion.py` approach) | **Legacy pattern — but keep it** | Simplest, most interpretable, and still defensible specifically *because* FedHeal's whole pitch is "a checkable second opinion, not a black box." Don't discard this for the sake of being current — it's a legitimate design choice, not just an outdated one |
| Early fusion (raw feature concatenation) | **Outdated** | Generally underperforms both late fusion and embedding-level fusion; rarely used anymore | — |

---

## 10. Reasoning / Explainability (the "why," not just the "what")

This category has aged less than the "solution model" categories above —
it's method-level, not architecture-level, so most of it remains current.
One genuinely new addition:

| Method | Status | Explains | Good fit for |
|---|---|---|---|
| **LLM-generated natural-language rationale** (e.g. MedGemma or a reasoning model producing a written differential) | **New since original catalog** | A readable clinical explanation, not just an attribution map or feature score | Turning any of the above predictions into the kind of narrative a clinician actually reads, rather than a heatmap alone |
| Grad-CAM / Grad-CAM++ | **Still current** | Which pixels/regions drove an image model's decision | Imaging specialists — still the standard first choice |
| SHAP | **Still current** | Per-feature contribution, any tabular/some deep models | Explaining XGBoost/LightGBM/TabPFN vitals predictions |
| LIME | **Still current** | Local, model-agnostic explanation | Quick explanations for any black-box model |
| Integrated Gradients | **Still current** | Theoretically grounded deep-net attribution | Imaging and text models |
| Attention visualization | **Still current** | What a transformer focused on | ViT, Swin, BEHRT-style models, and now MedGemma/CONCH |
| Counterfactual explanation | **Still current** | "What would need to change for the prediction to flip?" | Borderline cases, actionable clinician-facing framing |
| Causal inference (DoWhy, do-calculus) | **Still current** | Distinguishes correlation from causation | Deeper reasoning than pattern-matching |
| Bayesian Networks | **Still current** | Explicit probabilistic cause-effect reasoning | Traceable diagnostic reasoning chains |
| Knowledge graphs + ontologies (SNOMED CT, ICD-10, UMLS) | **Still current** | Grounds a prediction in formal medical knowledge | Linking a finding to diagnostic criteria |
| Rule-based / expert systems | **Still current** | Fully transparent, human-authored logic | Auditable logic where regulators require it |

---

## 11. Frameworks / libraries

| Framework | Status | Role |
|---|---|---|
| PyTorch | **Current** | Core deep learning — still the right choice; nothing has displaced it |
| **Hugging Face `transformers` + `timm`** | **Current, now the primary way to load foundation models** | This is how you'd actually pull in BiomedCLIP, MedGemma, UNI, Virchow2, CONCH etc. rather than hand-building architectures — most of Section 1–6's current-tier models ship as HF-loadable weights |
| **`tabpfn` / `tabpfn-extensions`** | **New, current** | The library for TabPFN v2/v2.5 — pip-installable, no GPU strictly required for smaller tables |
| MONAI | **Current** | Medical-imaging-specific PyTorch framework — still the right layer for nnU-Net-style segmentation pipelines and preprocessing |
| SHAP, Captum | **Current** | Explainability — unchanged |
| DoWhy / EconML | **Current** | Causal inference — unchanged |
| DGL / PyTorch Geometric | **Current** | Graph Neural Networks — unchanged |
| Flower (flwr) | **Current** | Federation layer — unchanged, and note it applies just as well to "federate a small head on top of frozen foundation-model embeddings," which is the pattern most sections above actually need |
| MLflow | **Current** | Experiment tracking |
| Hugging Face Transformers (for ClinicalBERT/BioBERT specifically) | **Legacy use case** | Still works, just superseded as the default choice by generative clinical LLMs for most of Section 6's use cases |

---

## 12. Disease-specific notes (updated)

### Breast cancer
- **Mammography imaging**: BiomedCLIP or CXRBase-style foundation embeddings + a lightweight fine-tuned head, in place of standalone EfficientNet/ResNet/DenseNet classification.
- **Histopathology (biopsy slides)**: UNI(v2)/Virchow2/Prov-GigaPath embeddings feeding a CLAM-style MIL head — this is the clearest upgrade path in the whole catalog, since your current zoo has no gigapixel whole-slide capability at all yet.
- **Genomic risk (BRCA1/2)**: Evo 2 and AlphaMissense for variant-effect prediction, AlphaFold3 for structural consequence — replaces Random Forest/SVM/autoencoder-on-expression as the primary method, with the classic approach kept as a cheap fallback for small cohorts.
- **Reasoning layer**: Grad-CAM (imaging) + SHAP (tabular) unchanged; add AlphaFold3's structural view and an LLM-generated narrative (MedGemma) as new reasoning outputs.

### Leukemia
- **Blood smear microscopy**: HoVer-Net/Cellpose for cell segmentation is *still current* — pair it with a foundation-model-embedding classifier for cell-type/morphology instead of a standalone CNN.
- **Flow cytometry**: TabPFN v2 in place of, or alongside, XGBoost/Random Forest on marker panels.
- **Cytogenetics / gene expression subtyping**: same genomic foundation-model upgrade path as breast cancer's genomic section.
- **Reasoning layer**: cell-level segmentation output stays inherently interpretable; layer SHAP on the tabular/genomic classifiers as before.

### General applicability (diseases not named yet)
Same principle as before, now with the foundation-model pattern folded in:
map the disease to a data modality (imaging/tabular/genomic/text/time-series),
pick the **current-tier** model from that section as the default (not the
legacy one), pick a reasoning method from Section 10, and register it in
`module5-modelzoo/registry.py`. The legacy models stay in this document as
documented fallbacks, not because they're wrong, but because low-resource
hospital sites without GPU/foundation-model access still need something
that runs.

---

## What's actually outdated *in your running code right now*

Everything above is the reference menu. This is the direct answer to
"remove outdated models" for what's actually implemented today:

| Currently in `module5-modelzoo` / `module6-condition-router` | Verdict | Swap to | Effort |
|---|---|---|---|
| `XGBoostVitalsModel` (tabular) | ✅ Addressed | `TabPFNVitalsModel` added alongside it as the current default (see `models/tabular_vitals_tabpfn.py`) | Done |
| `DenseNet201ChestXrayModel` | Legacy | `BiomedCLIP` or `CXRBase` embedding + head | **Medium** — needs HF `transformers`, a fine-tuning pass, no gated-weight approval needed |
| `ResNet50RetinaModel` | Legacy | `BiomedCLIP` embedding + head | **Medium** — same pattern as above |
| `EfficientNetSkinLesionModel` | Legacy but reasonable fallback | `BiomedCLIP` embedding + head | **Medium** — same pattern |
| `UNetSegmentationModel` | Legacy but reasonable fallback; `BiomedParse`/`SegVol` now added alongside it as current-tier options | `nnU-Net` (if labeled data is decent) or the newly-added `BiomedParse`/`SegVol` (prompted segmentation, no per-task training) | **Medium** for `BiomedParse`/`SegVol` — real loading code already exists (`models/foundation_biomedparse.py`, `models/foundation_segvol.py`), blocked only on GPU + `huggingface.co` access, not on writing more code |
| `RadFMModel`, `OmiCLIPModel` (newly added) | Real loading code, not runnable in this sandbox | N/A — blocked on infrastructure (GPU, HF network access), and RadFM's `predict()` on a real interface decision (generative, not classification) | See `docs/foundation-models-status.md` |
| Histopathology track (`module6-condition-router`'s `HistopathologyMILModel`) | ✅ Exists, but sklearn-family, not foundation-model-backed | `UNI`/`Virchow2`/`Prov-GigaPath` embeddings + MIL head (or `OmiCLIP` once its API is confirmed) | **Medium-High** — real upgrade path, not a from-scratch build anymore |
| *(still missing entirely)* | Gap, not outdated | Genomic variant track (Evo 2 / AlphaMissense / AlphaGenome) beyond the current sklearn-family `GenomicExpressionModel` | **New build** — directly relevant to your named BRCA1/2 and leukemia-cytogenetics use cases |

## How this gets used going forward

When a future stage asks for a new disease/specialist:
1. Identify the data modality (imaging/tabular/genomic/text/time-series) from the sections above.
2. Pick a **current-tier** solution model from the matching section as the default; fall back to the legacy tier only for low-resource deployments.
3. Pick a reasoning/explainability method from Section 10 to pair with it.
4. Register it in `module5-modelzoo/registry.py` following the existing `SpecialistModel` pattern — nothing about the router or fusion layer needs to change, including for foundation-model-backed specialists (they still just implement `predict()`).
