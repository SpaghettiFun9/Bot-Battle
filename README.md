# kevin_bot (v39)

An Agar.io competition bot that chooses each move by ray scoring - it casts 36 rays around its largest blob and scores every direction against food, prey, threats, viruses, and walls, then steers toward the best one.

**Threat handling:**
Enemy blobs are classified as prey, near-threats, or threats. Threats apply directional penalties and a hard veto over any ray that would step into a lethal blob's reach (including split-lunge range), while `flee_pressure` scales avoidance by proximity.

**Growth:**
Food is pursued with an early-game greed bonus that cancels the instant any flee pressure appears. Once past the virus-consume mass, the bot farms viruses to multiply — but only when a `safe_to_farm` check, using each rival's dynamic reach rather than a fixed radius, confirms no one can punish the split.

**Aggression:**
It split-attacks prey it can eat and snowballs harder as its mass and rank climb.

Deterministic, ~3 ms/turn.
