"""
Evo 2 specialist — fills the gap noted in docs/model-algorithm-catalog.md's
"What's actually outdated in your running code right now" table: *"(still
missing entirely) — Genomic variant track (Evo 2 / AlphaMissense /
AlphaGenome) beyond the current sklearn-family `GenomicExpressionModel`."*
This is a genuinely new capability, not a swap-in-place upgrade of that
model — see the "How this differs from GenomicExpressionModel" section
below before wiring it into module6.

Model: Evo 2 (Arc Institute / NVIDIA, Brixi et al., *Nature* 2026) — a DNA
foundation model trained on 9 trillion base pairs across all domains of
life, 1M-token context, single-nucleotide resolution. Per the catalog's
Section 5, it predicts the functional impact of variants — including
noncoding pathogenic mutations and clinically significant BRCA1/2
mutations — without task-specific fine-tuning (zero-shot, via the log-
likelihood-ratio scoring pattern in its own paper/repo).

Code: https://github.com/ArcInstitute/evo2, pip package `evo2`. Loading
pattern (copied from the repo's own published quick-start):

    from evo2 import Evo2
    evo2_model = Evo2("evo2_7b")
    score = evo2_model.score_sequences([reference_seq, alt_seq])

Weights ship on the Hugging Face Hub (`arcinstitute/evo2_7b` et al.) — the
same `huggingface.co` dependency every other foundation-model file in this
directory has. The 7B (smallest) checkpoint alone needs real GPU memory
(the repo's own README: "we currently only support ... H100 ... via
Docker"; even the 1B variant needs a modern GPU for practical latency) —
none of which is available in this sandbox, same constraints as RadFM/
BiomedParse/SegVol/OmiCLIP. This degrades to `StubSpecialistModel` via
registry.py's existing pattern. Real, correct, untested here.

## How this differs from GenomicExpressionModel (module6, Random Forest)

`GenomicExpressionModel` classifies a *gene-expression panel* (a fixed
vector of expression levels across ~20 genes) into a subtype/risk label —
useful, still current per the catalog (Section 5: "Random Forest/SVM on
gene-expression panels — still viable for small-N cohorts"), but a
different input entirely from what Evo 2 needs: a *DNA sequence* around a
specific variant call (chromosome, position, reference allele, alternate
allele — the kind of record a VCF file or a genetic-counseling workup
produces, not an expression microarray/RNA-seq panel). They are
complementary genomic tracks, not two implementations of the same task —
see module6-condition-router/EXPLANATION.md for how both get wired into
the same disease conditions (breast cancer / leukemia) side by side, each
firing when the caller has the matching kind of data for it.

## AlphaMissense / AlphaGenome as lighter-weight alternatives

The catalog lists these alongside Evo 2 for this section. Both differ from
Evo 2 in a way worth calling out for a future implementer: AlphaMissense
ships as a *precomputed scores database* (all possible human missense
variants, downloadable, no GPU/inference needed at request time — the
practical current pick for coding-variant pathogenicity when GPU access is
the constraint) rather than a model you run per-request; AlphaGenome
(DeepMind) is the noncoding/splice-variant specialist and, like Evo 2,
needs real inference compute. This file wires in Evo 2 specifically since
it's named first in the catalog and covers both the noncoding and BRCA1/2
cases named in the project's own instructions; swapping in AlphaMissense's
precomputed-table lookup as a lighter-weight `is_available()` path for
low-resource deployments is a reasonable follow-up, not done here to avoid
fabricating a scores-table integration this repo hasn't actually verified
(same "don't guess at an unverified API" standard applied to OmiCLIP).
"""
import os

try:
    from evo2 import Evo2
    EVO2_AVAILABLE = True
except (ImportError, OSError):
    EVO2_AVAILABLE = False

from base import PredictionResult, SpecialistModel

# Evo 2 scores a variant via log-likelihood-ratio between reference and
# alternate sequence, per its paper's own zero-shot variant-effect method.
# These thresholds are illustrative placeholders, in the same spirit as
# fusion.py's SEVERITY_WEIGHTS table — a clinical geneticist would need to
# calibrate real thresholds against a validation set of known-pathogenic /
# known-benign variants before this feeds a real decision.
CLASS_LABELS = ["likely_benign", "uncertain_significance", "likely_pathogenic"]


class Evo2VariantModel(SpecialistModel):
    name = "evo2-variant-effect-v1"
    modality = "genomic_variant"   # deliberately distinct from GenomicExpressionModel's "genomic" —
    task = "classification"        # see module docstring for why these are different input contracts

    def __init__(self, model_size: str = "evo2_7b"):
        if not EVO2_AVAILABLE:
            raise ImportError(
                f"{self.name} needs the `evo2` package, a GPU, and huggingface.co "
                "network access to fetch weights on first use. Install with "
                "`pip install evo2` on a machine with a supported GPU — see this "
                "module's docstring."
            )
        self.model_size = model_size
        self.model = Evo2(model_size)

    def is_available(self) -> bool:
        return EVO2_AVAILABLE

    def predict(self, case: dict) -> PredictionResult:
        """
        `case` expected: {"reference_sequence": "...", "alt_sequence": "...",
        "variant": {"chrom": ..., "pos": ..., "ref": ..., "alt": ...}} — a
        window of reference genome sequence around the variant call, and
        the same window with the alternate allele substituted in.
        Extracting that window from a raw VCF/BAM belongs in Module 2's
        genomic-track ingestion, not here — same division of labor as
        every other specialist in this zoo (case in, already preprocessed).

        Score = the log-likelihood-ratio Evo 2's own paper uses for
        zero-shot variant-effect prediction: how much less likely the
        alternate sequence is under the model than the reference sequence.
        A larger drop => more likely functionally disruptive.
        """
        ref_seq = case["reference_sequence"]
        alt_seq = case["alt_sequence"]

        ref_score, alt_score = self.model.score_sequences([ref_seq, alt_seq])
        llr = ref_score - alt_score   # positive => alt is less likely => more disruptive

        if llr > 2.0:
            label, confidence = "likely_pathogenic", min(1.0, llr / 4.0)
        elif llr < 0.5:
            label, confidence = "likely_benign", min(1.0, (0.5 - llr) / 0.5 + 0.5)
        else:
            label, confidence = "uncertain_significance", 0.5

        return PredictionResult(
            model_name=self.name,
            modality=self.modality,
            task=self.task,
            label=label,
            confidence=float(confidence),
            raw_output={"log_likelihood_ratio": float(llr), "ref_score": float(ref_score), "alt_score": float(alt_score)},
            explanation=f"Evo 2 log-likelihood-ratio (ref vs. alt) = {llr:.3f}",
            metadata={"variant": case.get("variant"), "model_size": self.model_size},
        )
