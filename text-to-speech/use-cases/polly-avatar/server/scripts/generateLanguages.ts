/**
 * OFFLINE generator: bakes the supported language/voice list to a static JSON
 * file the client ships with. Run when voices change.
 *
 * Usage: npx tsx src/generateLanguages.ts
 * Output: client/public/languages.json
 */
import { writeFileSync, mkdirSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import { getSupportedLanguages } from '../src/services/voicesService.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUTPUT = resolve(__dirname, '../../client/public/languages.json')

const langs = await getSupportedLanguages()
mkdirSync(dirname(OUTPUT), { recursive: true })
writeFileSync(OUTPUT, JSON.stringify(langs, null, 2))
console.log(`Wrote ${langs.length} languages to ${OUTPUT}`)
for (const l of langs) console.log(`  ${l.code} ${l.name} (${l.voices.length} voices)`)
