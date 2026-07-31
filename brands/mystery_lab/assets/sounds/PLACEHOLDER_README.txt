Place the real background music file here as:

    investigative.mp3

Matching brands/mystery_lab/config.yaml's music.local_file value
(assets/sounds/investigative.mp3). Per the Brand Manifesto's Music
Direction: low, tense, investigative -- low string drones, a
ticking-clock or clock-adjacent percussion motif, minimal piano.
Never a jump-scare sting; the tension is intellectual, not physical.

If this file is missing at runtime, LocalFileMusicProvider correctly
returns None (no music) rather than failing -- so the pipeline will
still run and publish without it, just silently, until you add one.
