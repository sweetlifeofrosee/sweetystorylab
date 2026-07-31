"""
core/pipeline/cli.py

The official entrypoint between an external trigger (GitHub Actions
cron) and the Story Engine. Deliberately thin: parse arguments, call
run_brand(), translate the outcome into a process exit code. No
brand-specific logic, no business logic, no scheduling logic -- all
scheduling stays in GitHub Actions workflow files, as agreed.

--count N is a developer/testing convenience (see run_brand_batch in
run.py): generates N independent stories, never publishes, saves each
story's full output to its own numbered folder under output/. Omit it
entirely and behavior is identical to before this flag existed --
single story, normal publish-or-dry-run path, same exit codes.

Exit codes (for GitHub Actions to branch on), unchanged from before:
  0 = pipeline completed and either published successfully or
      completed a valid dry run (expected for brands without a live
      Facebook Page/token yet -- not a failure).
  1 = pipeline crashed before completion (config error, API error,
      rendering error, etc.) -- something is broken and needs eyes.
  2 = pipeline completed end-to-end (video was generated) but the
      real publish attempt failed -- content exists locally but did
      not reach Facebook. Distinguished from exit 1 so GitHub Actions
      logs/alerts can tell "nothing was produced" apart from
      "something was produced but publishing failed."
--count mode always exits 0 or 1 (crash) -- there's no publish step
to fail, by design.
"""
import argparse
import sys

from .run import run_brand, run_brand_batch


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="sweetystorylab",
        description="Run the Story Engine pipeline for a single brand.",
    )
    parser.add_argument(
        "--brand", required=True,
        help="Brand id, matching a folder under brands/ (e.g. horror_lab)",
    )
    parser.add_argument(
        "--brands-root", default="brands",
        help="Root directory containing brand folders (default: brands)",
    )
    parser.add_argument(
        "--db-path", default="posts.db",
        help="Path to the SQLite log store (default: posts.db)",
    )
    parser.add_argument(
        "--count", type=int, default=None,
        help="Developer convenience: generate N stories, never publish, "
             "save each to its own numbered folder under output/. "
             "Omit for normal single-story behavior (unchanged).",
    )
    args = parser.parse_args(argv)

    if args.count is not None:
        try:
            run_brand_batch(
                brand_id=args.brand,
                count=args.count,
                brands_root=args.brands_root,
            )
        except Exception as e:
            print(f"[{args.brand}] BATCH GENERATION FAILED: {e}", file=sys.stderr)
            return 1
        return 0

    try:
        result = run_brand(
            brand_id=args.brand,
            brands_root=args.brands_root,
            db_path=args.db_path,
        )
    except Exception as e:
        print(f"[{args.brand}] PIPELINE FAILED before completion: {e}", file=sys.stderr)
        return 1

    publish_result = result["publish_result"]

    if publish_result.dry_run:
        print(f"[{args.brand}] Completed (dry run). {publish_result.detail}")
        return 0

    if publish_result.success:
        print(f"[{args.brand}] Published successfully. post_id={publish_result.post_id}")
        return 0

    print(f"[{args.brand}] Video generated but publish FAILED: {publish_result.detail}",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())