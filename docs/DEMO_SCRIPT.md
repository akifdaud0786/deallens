# DealLens demo video script (under 3 minutes)

Setup before recording:

1. Download the newest `deallens-evidence-<run_id>` artifact from GitHub Actions and extract it into `data/` (do not run `rebuild`).
2. Run `python -m deallens.cli serve` from the repository root and open http://127.0.0.1:8000.
3. Select **X1504VAP-BQ224WS**. Browser at 100% zoom, full screen.

Say only what the screen shows. If the coverage level has changed since this script was written, read the decision card as it is.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:15 | Top of the page: DealLens, tagline | "Price trackers tell you the cheapest price. DealLens tells you what today's price means, and how much evidence that judgement rests on." |
| 0:15–0:45 | Hero + decision card | "This is an ASUS Vivobook 15, exact model X1504VAP-BQ224WS. The lowest observed listed price is [read price] at [read seller]. Is it a good price? DealLens says: [read answer]. Here is why: [read the ✓ and ⚠ lines]." |
| 0:45–1:05 | Today's observed market | "Every price comes from Google Shopping via SerpApi. This seller shows a list price, but DealLens labels it as not verified. Stock is unknown because Shopping results do not state it." |
| 1:05–1:25 | What we know / don't know | "DealLens is explicit about what it knows and what it does not know yet. Honest uncertainty is part of the product." |
| 1:25–1:45 | Price history | If *Price history is building*: "History builds only from DealLens's own repeated observations; there is no back-filled data." If points are shown: "Each point is one real observation; points are not joined." |
| 1:45–2:10 | Why DealLens says this → open one "View evidence details" | "Every claim is deterministic and traceable: claim ID, SerpApi search ID, raw response hash and timestamp." |
| 2:10–2:30 | Evidence coverage + active tracking plan | "Coverage counts observed calendar days, production runs and independent sellers. Historical claims unlock only past fixed thresholds. Collection runs on GitHub Actions three times a day, one Google Shopping call per slot, with a credit guard." |
| 2:30–2:45 | Click **X1504VA-NJ2324WS** | "When the active plan has not observed a product, DealLens says so instead of showing an old price as current." |
| 2:45–2:58 | Footer | "DealLens: observed data only, no all-time-low claims, no predictions. Built on SerpApi." |

Keep the recording under 3:00. Upload as unlisted on YouTube (or a Google Drive link with view access) and paste the link into `docs/SUBMISSION.md` and the form.
