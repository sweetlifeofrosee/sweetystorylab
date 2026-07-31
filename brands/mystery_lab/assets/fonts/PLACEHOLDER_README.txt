Place the real font file here as:

    PlayfairDisplay-Regular.ttf

Matching brands/mystery_lab/config.yaml's branding.font value
(assets/fonts/PlayfairDisplay-Regular.ttf) and branding.font_source_url,
which points to:

    https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf

Same pattern as Horror Lab: this file is not meant to be committed
directly if you'd rather fetch it fresh in the GitHub Actions workflow
(recommended, matching Horror Lab's approach) -- add a "Download font"
step to mystery_lab's workflow that curls it to this exact path before
the pipeline runs. If you'd rather commit the actual font file to the
repo instead, that works too -- just place it here and delete this
placeholder.
