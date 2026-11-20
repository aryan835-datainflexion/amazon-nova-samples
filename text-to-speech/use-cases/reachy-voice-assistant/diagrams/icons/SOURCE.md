# Icon provenance

All AWS icons are from the official **AWS Architecture Icons** package
(https://aws.amazon.com/architecture/icons/), release `Icon-package_07312026`,
rasterised from SVG with `rsvg-convert -h 384 -a`.

| File | Source SVG (in the package) | Represents |
| --- | --- | --- |
| `transcribe.png` | `Architecture-Service-Icons_*/Arch_Artificial-Intelligence/48/Arch_Amazon-Transcribe_48.svg` | Amazon Transcribe |
| `bedrock.png` | `Architecture-Service-Icons_*/Arch_Artificial-Intelligence/48/Arch_Amazon-Bedrock_48.svg` | Amazon Bedrock |
| `polly.png` | `Architecture-Service-Icons_*/Arch_Artificial-Intelligence/48/Arch_Amazon-Polly_48.svg` | Amazon Polly |
| `user.png` | `Resource-Icons_*/Res_General-Icons/Res_48_Light/Res_User_48_Light.svg` | The person talking to the assistant |

No official icon exists for the local **pipecat app**, the **ReachyDriver**
processor, or the **Reachy Mini** robot, so those tiles use lettered/glyph tiles
rather than a borrowed (and therefore misleading) icon.

Regenerate the diagram: `python diagrams/render_architecture.py`
