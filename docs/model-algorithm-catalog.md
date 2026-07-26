# FedHeal — Model / Algorithm / Framework Catalog

**Purpose of this document:** every future stage/week of development pulls
its model choices from (or explicitly extends) this list. It's not limited
to what's already implemented in `module5-modelzoo` — that module currently
uses only 5 of the entries below (XGBoost, DenseNet201, ResNet50,
EfficientNet, U-Net). This document is the full menu.

Two things every disease-specific pipeline needs, per the project's own
framing ("a prediction a doctor can check, not a black box"):
1. **A solution model** — something that outputs a diagnosis/risk/finding.
2. **A reasoning/explainability method** — something that shows *why*.

The catalog below is organized by data modality first (since that's how
the router already dispatches), then a separate section for reasoning/XAI
methods that layer on top of any of them, then frameworks/libraries, then
disease-specific notes for the two you named plus general applicability.

---

## 1. Imaging — classification (2D: X-ray, retina, skin, mammogram, etc.)

| Model family | Notes | Good fit for |
|---|---|---|
| ResNet (18/50/101/152) | Already in zoo (ResNet50) | General-purpose backbone, retina, skin |
| DenseNet (121/169/201) | Already in zoo (201) | Chest X-ray, dense feature reuse helps with subtle findings |
| EfficientNet (B0-B7) | Already in zoo (B0) | Skin lesions; scales accuracy vs. compute cleanly |
| Inception v3 / v4 | Named in original proposal alongside EfficientNet | Skin lesion, general classification |
| VGG16/19 | Older, simple, still used as a baseline in medical imaging papers | Baselines, quick prototyping |
| Vision Transformer (ViT) | Attention-based, needs more data/pretraining than CNNs | Large datasets, transfer from ImageNet-21k |
| Swin Transformer | Hierarchical ViT variant, better than plain ViT on smaller datasets | Same use cases as ViT, more data-efficient |
| ConvNeXt | Modernized CNN competing with ViT | General classification, strong modern baseline |
| MobileNet (v2/v3) | Lightweight — runs on-device | Mobile/edge deployment at a hospital with weak hardware |
| SqueezeNet | Very lightweight | Edge deployment, embedded diagnostic devices |
| Capsule Networks (CapsNet) | Better at preserving spatial relationships than CNNs | Some published mammography/lung-nodule work |
| Ensemble CNN (e.g. ResNet+DenseNet+EfficientNet voting) | Combine multiple imaging backbones for one modality | Boosting accuracy where a single model plateaus |

## 2. Imaging — segmentation (tumor/organ boundaries, lesion outlines)

| Model family | Notes | Good fit for |
|---|---|---|
| U-Net | Already in zoo (custom) | General medical segmentation gold standard |
| U-Net++ | Nested skip connections, improves on vanilla U-Net | Finer boundary detection |
| Attention U-Net | Adds attention gates to skip connections | Focusing on small/subtle lesions |
| V-Net | 3D variant of U-Net | Volumetric CT/MRI segmentation |
| Mask R-CNN | Instance segmentation (separates multiple objects, not just a mask) | Counting/segmenting multiple nodules or cells in one image |
| DeepLab (v3/v3+) | Atrous/dilated convolutions for multi-scale context | Organ segmentation, histopathology region segmentation |
| nnU-Net | Self-configuring U-Net framework, widely used in medical imaging competitions | When you want a strong segmentation baseline with minimal tuning |
| SAM (Segment Anything Model) / MedSAM | Foundation segmentation model fine-tuned for medical images | Rapid prototyping segmentation with less labeled data |

## 3. Whole-slide / histopathology imaging (relevant directly to breast cancer, leukemia blood smears)

| Model family | Notes | Good fit for |
|---|---|---|
| Multiple Instance Learning (MIL / CLAM) | Handles gigapixel whole-slide images without patch-level labels | Breast cancer histopathology (e.g. BACH, CAMELYON datasets), any biopsy slide diagnosis |
| Patch-based CNN + aggregation | Split slide into patches, classify each, aggregate | Simpler alternative to full MIL pipelines |
| Graph Neural Networks (GNN) on cell graphs | Model spatial relationships between cells/nuclei | Tumor microenvironment analysis, cell-interaction reasoning |
| HoVer-Net | Nucleus segmentation + classification in one model | Counting/classifying cell types in blood smears (leukemia) or tissue |
| Cellpose / StarDist | Cell/nucleus segmentation specifically | Blood smear cell counting and morphology (leukemia diagnosis workflows) |

## 4. Structured / tabular data (vitals, labs, EHR structured fields)

| Model family | Notes | Good fit for |
|---|---|---|
| XGBoost | Already in zoo | General tabular clinical prediction |
| LightGBM | Faster on large tabular data, already in requirements.txt (unused yet) | Larger EHR tabular datasets |
| CatBoost | Handles categorical features natively without manual encoding | EHR data with many categorical fields (diagnosis codes, med names) |
| Random Forest | Simple, robust, easy to explain via feature importance | Baseline models, smaller datasets |
| Logistic Regression / SGDClassifier | Already used in module3 (federated) | Simple, interpretable, federation-friendly baseline |
| Support Vector Machine (SVM) | Strong on small-to-medium, high-dimensional tabular/genomic data | Gene-expression classification, small clinical cohorts |
| TabNet | Deep learning architecture built specifically for tabular data with built-in feature attention | When you want a neural net that's still interpretable via attention masks |
| Multi-Layer Perceptron (MLP) | Simple neural net baseline | Structured data when boosting isn't preferred |

## 5. Genomic / omics data (relevant directly to leukemia subtyping, breast cancer BRCA risk)

| Model family | Notes | Good fit for |
|---|---|---|
| Random Forest / SVM on gene expression | Classic approach, still competitive on small-N high-dimensional omics data | Leukemia subtype classification from gene expression panels |
| Autoencoders (for dimensionality reduction) | Compress high-dimensional omics data before feeding a classifier | Preprocessing genomic data for any downstream classifier |
| Variational Autoencoders (VAE) | Same as above, plus generative capability | Data augmentation for rare genomic subtypes |
| Graph Neural Networks on gene/protein interaction networks | Model biological pathway relationships | Reasoning about *why* a mutation matters (pathway-level explanation) |
| Deep learning on multi-omics fusion (e.g. MOFA, DeepOmix-style architectures) | Combine genomics + transcriptomics + clinical data | Precision oncology risk scoring |

## 6. Clinical text / NLP (doctor's notes, radiology reports, discharge summaries)

| Model family | Notes | Good fit for |
|---|---|---|
| ClinicalBERT | BERT pretrained on clinical notes (MIMIC-III) | Extracting structured info from unstructured clinical notes |
| BioBERT | BERT pretrained on biomedical literature (PubMed) | Biomedical entity recognition, literature-grounded reasoning |
| BlueBERT | Pretrained on PubMed + MIMIC-III combined | Mixed biomedical + clinical text tasks |
| Named Entity Recognition (NER) models (spaCy sci/med models, MedCAT) | Extract symptoms/diagnoses/medications from free text | Turning unstructured notes into structured features for Module 2 |
| GPT-style clinical LLMs (e.g. fine-tuned open models) | Summarization, report generation, reasoning over combined text+structured data | Generating the "reasoning" narrative a clinician reads alongside a prediction |

## 7. Time-series / sequential EHR data

| Model family | Notes | Good fit for |
|---|---|---|
| LSTM / GRU | Classic sequence models | Modeling vitals over time, admission trajectories |
| Temporal Convolutional Networks (TCN) | Convolution-based alternative to RNNs, often faster to train | Same use cases as LSTM/GRU |
| Transformer-based EHR models (e.g. BEHRT, Med-BERT) | Attention over sequences of clinical events/codes | Predicting future risk from a patient's full visit history |

## 8. Survival analysis (time-to-event: relapse, progression, mortality)

| Model family | Notes | Good fit for |
|---|---|---|
| Cox Proportional Hazards | Classic statistical survival model | Baseline survival/prognosis modeling, still standard in clinical papers |
| Random Survival Forest | Tree-based survival model, handles nonlinearity | More complex prognosis modeling than Cox alone |
| DeepSurv | Neural-network extension of Cox PH | When you have enough data to justify a deep model for prognosis |
| Kaplan-Meier estimation | Non-parametric, used for descriptive survival curves, not prediction per se | Baseline/reporting alongside any of the above |

## 9. Multi-modal fusion (combining imaging + tabular + genomic + text for one patient)

| Approach | Notes |
|---|---|
| Late fusion (current `fusion.py` approach) | Each modality's model runs independently, combine outputs/scores at the end — simplest, most interpretable |
| Early fusion | Concatenate raw/embedded features from each modality before one shared model — needs aligned data |
| Intermediate/joint embedding fusion | Each modality has its own encoder producing an embedding; a shared layer combines embeddings (not raw outputs) | More expressive than late fusion, harder to train/explain |
| Attention-based multi-modal fusion (e.g. cross-modal attention transformers) | Lets the model learn which modality matters most per case | State-of-the-art multi-modal medical AI, needs more data |

---

## 10. Reasoning / Explainability (the "why," not just the "what")

This is the category most directly tied to your requirement that the AI
find both **solution and reason**. These layer on top of any model above.

| Method | Explains | Good fit for |
|---|---|---|
| Grad-CAM / Grad-CAM++ | Which pixels/regions drove an image model's decision | Already planned in the proposal for the imaging specialists |
| SHAP (SHapley Additive exPlanations) | Per-feature contribution to any model's output (tabular, genomic, even some deep models) | Explaining XGBoost/LightGBM vitals predictions — already partially done via `feature_importances_` in `tabular_vitals.py`, SHAP is the more rigorous version |
| LIME | Local, model-agnostic explanation by perturbing inputs | Quick explanations for any black-box model, imaging or tabular |
| Integrated Gradients | Attribution method for deep nets, more theoretically grounded than raw saliency maps | Imaging and text models alike |
| Attention visualization | Show what a transformer/attention-based model focused on | ViT, Swin, BEHRT, ClinicalBERT-style models |
| Counterfactual explanation | "What would need to change for the prediction to flip?" | Explaining borderline cases to clinicians in actionable terms |
| Causal inference models (e.g. causal graphs, do-calculus, DoWhy library) | Distinguish correlation from causation in risk factors | Deeper "reasoning" than pattern-matching — e.g. does a factor actually cause the outcome |
| Bayesian Networks | Explicit probabilistic reasoning over cause-effect relationships between symptoms/findings | Diagnostic reasoning chains a clinician can trace step by step |
| Knowledge graphs + medical ontologies (SNOMED CT, ICD-10, UMLS) | Ground a prediction in structured medical knowledge, not just learned statistics | Linking a finding to formal diagnostic criteria, supporting the "reason" requirement directly |
| Rule-based / expert systems (e.g. clinical decision rules encoded explicitly) | Fully transparent, human-authored reasoning | Combining with ML for cases where regulators/clinicians need auditable logic, not just a statistical model |

---

## 11. Frameworks / libraries (beyond what's already used)

| Framework | Role |
|---|---|
| PyTorch / TensorFlow | Already in use (PyTorch) — core deep learning |
| **MONAI** | Medical-imaging-specific framework built on PyTorch — pre-built transforms, losses, and models tuned for medical images (segmentation, classification). Worth adopting instead of raw torchvision for the imaging specialists. |
| Hugging Face Transformers | For ClinicalBERT/BioBERT/BlueBERT and any clinical NLP work |
| scikit-survival | Survival analysis models (Cox PH, Random Survival Forest) in a scikit-learn-compatible API |
| SHAP (library) | Explainability, works with XGBoost/LightGBM/sklearn/some deep models |
| Captum | PyTorch's official interpretability library (Grad-CAM, Integrated Gradients, attention viz) |
| DoWhy / EconML | Causal inference libraries |
| DGL / PyTorch Geometric | Graph Neural Network libraries — for cell graphs, gene/protein interaction networks |
| Cellpose / StarDist (as libraries) | Pretrained cell/nucleus segmentation, usable directly or fine-tuned |
| Flower (flwr) | Already in use — federation layer, applies to ANY of the models above, not just XGBoost/logistic regression |
| MLflow | Experiment tracking across all these models as the model zoo grows |

---

## 12. Disease-specific notes

### Breast cancer
- **Mammography imaging**: EfficientNet/ResNet/DenseNet classification, or dedicated breast-imaging architectures from published work (e.g. models trained on CBIS-DDSM, INbreast datasets).
- **Histopathology (biopsy slides)**: MIL/CLAM on whole-slide images (BACH, CAMELYON16/17 datasets) — this is a strong candidate for a new specialist in the zoo, distinct from the current imaging models which are all single-image classifiers, not gigapixel slide handlers.
- **Genomic risk (BRCA1/2, gene expression subtyping)**: Random Forest/SVM/autoencoder-based approaches on gene expression panels (e.g. METABRIC dataset).
- **Reasoning layer**: Grad-CAM on the imaging side, SHAP on any tabular risk-factor model, knowledge-graph grounding against BRCA/oncology ontologies for the genomic side.

### Leukemia
- **Blood smear microscopy**: CNN classification (white blood cell type/morphology) — HoVer-Net or Cellpose for individual cell segmentation before classification, since leukemia diagnosis is fundamentally about cell counts/morphology, not whole-image classification.
- **Flow cytometry data**: Structured/tabular models (XGBoost, Random Forest) on flow cytometry marker panels.
- **Cytogenetics / gene expression subtyping**: Same genomic approaches as breast cancer's genomic section — Random Forest/SVM/autoencoders on expression data, since leukemia subtypes (e.g. ALL vs AML, further molecular subtypes) are heavily gene-expression-driven.
- **Reasoning layer**: Cell-level segmentation + count outputs are inherently more interpretable than a single "cancer/no cancer" label; layer SHAP on top of the tabular/genomic classifiers.

### General applicability (diseases not named yet)
The catalog above is intentionally organized by **data modality and task type**, not by disease, precisely so it generalizes: any new disease request maps to "what data do we have" (imaging? tabular? genomic? text? time-series?) and "what do we need" (classification? segmentation? survival/prognosis? risk score?) — then the router pulls the matching model family from this document, and a reasoning method from Section 10 gets attached. New diseases should extend this table, not require a new document.

---

## How this gets used going forward

When a future stage asks for a new disease/specialist:
1. Identify the data modality (imaging/tabular/genomic/text/time-series) from the sections above.
2. Pick a solution model from the matching section (default to what's already in the zoo — ResNet/DenseNet/EfficientNet/U-Net/XGBoost — unless the disease specifically calls for something else, like MIL for histopathology or a survival model for prognosis).
3. Pick a reasoning/explainability method from Section 10 to pair with it.
4. Register it in `module5-modelzoo/registry.py` following the existing `SpecialistModel` pattern — nothing about the router or fusion layer needs to change.
