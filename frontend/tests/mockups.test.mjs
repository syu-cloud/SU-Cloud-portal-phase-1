import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import { test } from 'node:test'

test('다섯 목업 사본은 스크립트 없는 읽기 전용 미리보기다', async () => {
  const directory = new URL('../public/mockups/', import.meta.url)
  const files = (await readdir(directory)).filter(name => name.endsWith('.html')).sort()
  assert.deepEqual(files, ['console.html', 'login.html', 'mypage.html', 'portal.html', 'signup.html'])
  for (const file of files) {
    const html = await readFile(new URL(file, directory), 'utf8')
    assert.doesNotMatch(html, /<script\b/i, file)
    assert.doesNotMatch(html, /\son[a-z]+\s*=/i, file)
    assert.match(html, /<div inert>/, file)
    assert.doesNotMatch(html, /fonts\.googleapis\.com/, file)
  }
})
