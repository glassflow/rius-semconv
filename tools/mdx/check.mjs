// Compiles every page under a docs-site directory (default out/docs-site/)
// with @mdx-js/mdx and the remark plugins the docs site's Nextra build uses,
// so a page that would break the glassflow-docs build fails here instead.
// Also checks the navigation: every _meta.tsx entry has a page directory, and
// every page directory has an entry.
//
//     npm ci --prefix tools/mdx && node tools/mdx/check.mjs [dir]
//
// Exits 1 on the first page that fails to compile or on a navigation
// mismatch, after reporting every problem.
import { compile } from '@mdx-js/mdx'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import remarkFrontmatter from 'remark-frontmatter'
import remarkGfm from 'remark-gfm'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const dir = path.resolve(process.argv[2] ?? path.join(root, 'out', 'docs-site'))

async function walk(d) {
  const out = []
  for (const entry of await readdir(d, { withFileTypes: true })) {
    const p = path.join(d, entry.name)
    if (entry.isDirectory()) out.push(...(await walk(p)))
    else out.push(p)
  }
  return out.sort()
}

const problems = []
const files = await walk(dir)
const pages = files.filter((f) => f.endsWith('.mdx'))
if (pages.length === 0) problems.push(`${dir}: no .mdx pages`)

for (const file of pages) {
  const rel = path.relative(root, file)
  if (path.basename(file) !== 'page.mdx') {
    problems.push(`${rel}: a Nextra app-router page must be named page.mdx`)
    continue
  }
  try {
    await compile(await readFile(file, 'utf8'), {
      remarkPlugins: [remarkFrontmatter, remarkGfm],
    })
  } catch (err) {
    const where = err.place?.start?.line ?? err.line
    problems.push(`${rel}${where ? `:${where}` : ''}: ${err.reason ?? err.message}`)
  }
}

// The keys the docs site's generate-llms.mjs reads: single-quoted, one per entry.
for (const meta of files.filter((f) => path.basename(f) === '_meta.tsx')) {
  const d = path.dirname(meta)
  const keys = [...(await readFile(meta, 'utf8')).matchAll(/'([^']+)'\s*:/g)].map((m) => m[1])
  const dirs = (await readdir(d, { withFileTypes: true }))
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
  for (const k of keys.filter((k) => !dirs.includes(k))) {
    problems.push(`${path.relative(root, meta)}: '${k}' has no page directory`)
  }
  for (const k of dirs.filter((k) => !keys.includes(k))) {
    problems.push(`${path.relative(root, meta)}: no entry for the page directory '${k}'`)
  }
}

if (problems.length > 0) {
  for (const p of problems) console.error(p)
  process.exit(1)
}
console.log(`${path.relative(root, dir) || '.'}: ${pages.length} page(s) compile`)
