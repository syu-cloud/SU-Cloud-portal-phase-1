import assert from 'node:assert/strict'
import { test } from 'node:test'
import { apiRequest, mailHelp } from '../src/api.ts'

test('CSRF 발급은 같은 출처의 쿠키와 GET을 사용한다', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/v1/auth/csrf')
    assert.equal(options.method, 'GET')
    assert.equal(options.credentials, 'same-origin')
    assert.equal(options.body, undefined)
    return Response.json({ csrf_token: 'test-csrf' })
  })
  assert.equal((await apiRequest('csrf')).body.csrf_token, 'test-csrf')
})

test('가입 POST는 CSRF와 문자열 학번을 유지한다', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/v1/auth/signup')
    assert.equal(options.method, 'POST')
    assert.equal(options.headers['X-CSRFToken'], 'test-csrf')
    assert.equal(options.headers['Content-Type'], 'application/json')
    assert.equal(JSON.parse(options.body).login_id, '001234')
    return Response.json({ user: { login_id: '001234' } }, { status: 201 })
  })
  assert.equal((await apiRequest('signup', { login_id: '001234' }, 'test-csrf')).status, 201)
})

test('CSRF 누락 점검은 실제로 헤더를 생략하고 403 응답을 보존한다', async t => {
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    assert.equal('X-CSRFToken' in options.headers, false)
    return Response.json({ error: { code: 'CSRF_FAILED', message: 'CSRF 토큰을 확인해 주세요.' } }, { status: 403 })
  })
  const result = await apiRequest('signup', {})
  assert.equal(result.status, 403)
  assert.equal(result.body.error.code, 'CSRF_FAILED')
})

test('재발급 제한의 상태·대기 시간을 그대로 반환한다', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ error: { code: 'COOLDOWN_ACTIVE', details: { retry_after_seconds: 59 } } }, { status: 429 }))
  const result = await apiRequest('signup/email-challenge', {})
  assert.equal(result.status, 429)
  assert.equal(result.body.error.details.retry_after_seconds, 59)
})

test('HTML 오류 페이지를 서버 JSON으로 표시하지 않는다', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('<h1>proxy error</h1>', { status: 500 }))
  await assert.rejects(apiRequest('signup', {}), /JSON 응답을 받지 못했습니다/)
})

test('잘못된 JSON 응답 형식을 거절한다', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json([]))
  await assert.rejects(apiRequest('signup', {}), /응답 형식/)
})

test('SMTP 안내는 학교 수신함·스팸함을 사용하고 파일 안내를 표시하지 않는다', () => {
  const help = mailHelp('smtp')
  assert.match(help.description, /수신함/)
  assert.match(help.description, /스팸함/)
  assert.doesNotMatch(JSON.stringify(help), /\.local\/mail/)
  assert.doesNotMatch(help.sent, /수신되었습니다/)
})

test('파일 모드로 전환하면 개발용 메일 확인 방법을 안내한다', () => {
  assert.match(mailHelp('file').description, /\.local\/mail/)
})

test('알 수 없는 방식은 SMTP 발송으로 단정하지 않는다', () => {
  assert.match(mailHelp(undefined).description, /확인 방식/)
  assert.doesNotMatch(mailHelp('other').description, /메일을 보냈/)
})
