import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { apiRequest, mailHelp } from './api'
import type { ApiResult } from './api'
import './App.css'

type Action = 'issue' | 'verify' | 'signup'
type Profile = { name: string; department: string; login_id: string; school_email: string; password: string; password_confirm: string }
type Challenge = { flow_id: string; challenge_id: string; target_email: string; expires_at: string; resend_available_at: string }
type Grant = { school_email: string; grant_expires_at: string }
type User = { user_id: string; login_id: string; school_email: string; name: string; account_role: string; member_type: string; notification_email_type: string }
type ApiError = { code: string; message: string; details?: { fields?: Record<string, string>; retry_after_seconds?: number } }
const emptyProfile: Profile = { name: '', department: '', login_id: '', school_email: '', password: '', password_confirm: '' }
const paths: Record<Action, string> = { issue: 'signup/email-challenge', verify: 'signup/email-challenge/verify', signup: 'signup' }
const labels: Record<Action, string> = { issue: '인증번호 발급', verify: '인증 확인', signup: '회원가입' }
const previews = { signup: '회원가입', login: '로그인', portal: '포털', mypage: '마이페이지', console: '콘솔' }
const canonical = (email: string) => email.trim().toLowerCase()
const remaining = (deadline: string | undefined, now: number) => deadline ? Math.max(0, Math.ceil((Date.parse(deadline) - now) / 1000)) : 0
const duration = (seconds: number) => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

function App() {
  const [form, setForm] = useState<Profile>(emptyProfile)
  const [code, setCode] = useState('')
  const [token, setToken] = useState('')
  const [mailDelivery, setMailDelivery] = useState<unknown>()
  const [connecting, setConnecting] = useState(true)
  const [flowId, setFlowId] = useState<string | null>(null)
  const [challenge, setChallenge] = useState<Challenge | null>(null)
  const [resendAt, setResendAt] = useState<string>()
  const [grant, setGrant] = useState<Grant | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [now, setNow] = useState(() => Date.now())
  const [notice, setNotice] = useState({ error: false, message: 'API에 연결하고 있습니다.' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [history, setHistory] = useState<(ApiResult & { label: string })[]>([])
  const [action, setAction] = useState<Action>('issue')
  const [draft, setDraft] = useState('{}')
  const [omitCsrf, setOmitCsrf] = useState(false)
  const [preview, setPreview] = useState<keyof typeof previews | null>(null)
  const previewDialog = useRef<HTMLDialogElement>(null)
  const bootstrap = useRef<Promise<ApiResult> | null>(null)

  useEffect(() => {
    let active = true
    // StrictMode에서 최초 세션 발급 요청이 두 번 전송되지 않게 공유한다.
    bootstrap.current ??= apiRequest('csrf')
    bootstrap.current.then(result => {
      if (!active) return
      if (result.status !== 200 || typeof result.body.csrf_token !== 'string') throw new Error('CSRF 토큰 발급에 실패했습니다.')
      setToken(result.body.csrf_token)
      setMailDelivery(result.body.email_delivery)
      setNotice({ error: false, message: '학교 이메일 인증을 시작해 주세요.' })
    }).catch(() => {
      if (active) setNotice({ error: true, message: 'API 연결에 실패했습니다. Django를 실행한 뒤 CSRF 연결을 다시 시도해 주세요.' })
    }).finally(() => { if (active) setConnecting(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const cooldown = remaining(resendAt, now)
  const codeSeconds = remaining(challenge?.expires_at, now)
  const grantSeconds = remaining(grant?.grant_expires_at, now)
  const sameEmail = !!challenge && canonical(form.school_email) === challenge.target_email
  const verified = !!grant && canonical(form.school_email) === grant.school_email && grantSeconds > 0
  const disabled = busy || connecting || !token
  const mail = mailHelp(mailDelivery)

  function record(result: ApiResult, label: string) {
    const body = { ...result.body }
    if ('csrf_token' in body) body.csrf_token = '(발급됨)'
    setHistory(previous => [{ ...result, body, label }, ...previous].slice(0, 6))
  }

  function payload(selected: Action): Record<string, unknown> {
    if (selected === 'issue') return { flow_id: flowId, school_email: form.school_email }
    const ids = { flow_id: flowId, challenge_id: challenge?.challenge_id ?? '', school_email: form.school_email }
    if (selected === 'verify') return { ...ids, verification_code: code }
    return { ...ids, ...form }
  }

  function applyResult(selected: Action, body: Record<string, unknown>) {
    if (selected === 'issue') {
      const issued = body as unknown as Challenge
      setChallenge(issued)
      setFlowId(issued.flow_id)
      setResendAt(issued.resend_available_at)
      setGrant(null)
      setCode('')
      setUser(null)
      setForm(previous => ({ ...previous, school_email: issued.target_email }))
    } else if (selected === 'verify') {
      setGrant(body as unknown as Grant)
    } else {
      setUser(body.user as User)
      setForm(previous => ({ ...previous, password: '', password_confirm: '' }))
      setCode('')
    }
  }

  async function perform(selected: Action, body = payload(selected), omit = false, count = 1) {
    setBusy(true)
    setErrors({})
    try {
      const settled = await Promise.allSettled(Array.from({ length: count }, () => apiRequest(paths[selected], body, omit ? undefined : token)))
      const results = settled.flatMap(result => result.status === 'fulfilled' ? [result.value] : [])
      if (results.length === 0) throw new Error('API 응답을 받지 못했습니다. 서버 연결을 확인해 주세요.')
      results.forEach((result, index) => record(result, `${labels[selected]}${count > 1 ? ` ${index + 1}` : ''}`))
      const success = results.find(result => result.status >= 200 && result.status < 300)
      if (success) applyResult(selected, success.body)
      if (count > 1) {
        setNotice({ error: !success, message: `동시 요청 완료: ${results.map(result => `HTTP ${result.status}`).join(' / ')}${results.length < count ? ' / 일부 응답 수신 실패' : ''}. 아래 응답에서 결과를 확인하세요.` })
      } else if (success) {
        setNotice({ error: false, message: selected === 'issue' ? mail.sent : selected === 'verify' ? '인증되었습니다. 가입 정보 입력을 마쳐 주세요.' : '포털 계정이 생성되었습니다.' })
      } else {
        const error = results[0].body.error as ApiError | undefined
        setErrors(error?.details?.fields ?? {})
        setNotice({ error: true, message: `${error?.message ?? '요청에 실패했습니다.'}${error?.code ? ` (${error.code})` : ''}${error?.details?.retry_after_seconds ? ` · ${error.details.retry_after_seconds}초 후 재시도` : ''}` })
      }
    } catch (error) {
      setNotice({ error: true, message: error instanceof Error ? error.message : '서버 연결을 확인해 주세요.' })
    } finally {
      setBusy(false)
      setNow(Date.now())
    }
  }

  async function reconnect() {
    setConnecting(true)
    try {
      const result = await apiRequest('csrf')
      record(result, 'CSRF 연결')
      if (result.status !== 200 || typeof result.body.csrf_token !== 'string') throw new Error('CSRF 토큰 발급에 실패했습니다.')
      setToken(result.body.csrf_token)
      setMailDelivery(result.body.email_delivery)
      setNotice({ error: false, message: 'CSRF 연결을 갱신했습니다.' })
    } catch {
      setNotice({ error: true, message: 'Django(8000)가 실행 중인지 확인해 주세요.' })
    } finally { setConnecting(false) }
  }

  function edit(field: keyof Profile, value: string) {
    setForm(previous => ({ ...previous, [field]: value }))
    setErrors(previous => ({ ...previous, [field]: '' }))
    if (field === 'school_email' && canonical(value) !== canonical(form.school_email)) {
      setGrant(null)
      setCode('')
    }
  }

  function reset(example = false) {
    const unique = Date.now().toString()
    setForm(example ? { name: '홍길동', department: '컴퓨터공학부', login_id: `00${unique}`, school_email: mailDelivery === 'file' ? `dev.${unique}@syuin.ac.kr` : '', password: 'LocalTest1!', password_confirm: 'LocalTest1!' } : emptyProfile)
    setCode('')
    setFlowId(null)
    setChallenge(null)
    setGrant(null)
    setUser(null)
    setErrors({})
    setDraft('{}')
    setNotice({ error: false, message: example ? '새 예시 정보를 입력했습니다. 실제 메일 모드에서는 본인의 학교 이메일을 직접 입력해 주세요.' : '입력을 초기화했습니다. 생성된 계정과 서버의 대기·요청 제한은 유지됩니다.' })
  }

  function prepareDraft(selected = action) {
    const body = payload(selected)
    delete body.password
    delete body.password_confirm
    setDraft(JSON.stringify(body, null, 2))
  }

  function runTool(count = 1) {
    try {
      const body = JSON.parse(draft)
      if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('JSON 객체가 필요합니다.')
      // 점검용 편집기에 비밀번호를 복제하지 않고 가입 폼에서만 가져온다.
      if (action === 'signup') Object.assign(body, { password: form.password, password_confirm: form.password_confirm })
      void perform(action, body, omitCsrf, count)
    } catch {
      setNotice({ error: true, message: '점검 요청을 올바른 JSON 객체로 입력해 주세요.' })
    }
  }

  function field(key: keyof Profile, label: string, autoComplete: string, help?: string) {
    const password = key === 'password' || key === 'password_confirm'
    return <div className={`field ${key === 'login_id' || password ? 'full' : ''}`}>
      <label htmlFor={key}>{label}<span aria-hidden="true"> *</span></label>
      <input id={key} name={key} value={form[key]} onChange={event => edit(key, event.target.value)} disabled={busy} type={password && !showPassword ? 'password' : 'text'} autoComplete={autoComplete} aria-invalid={!!errors[key]} aria-describedby={`${key}-help ${key}-error`} />
      <p id={`${key}-help`} className="helper">{help}</p>
      <p id={`${key}-error`} className="field-error">{errors[key]}</p>
    </div>
  }

  function openPreview(value: keyof typeof previews) {
    setPreview(value)
    previewDialog.current?.showModal()
  }

  return <>
    <header className="topbar"><a className="brand" href="/" aria-label="SU Cloud 회원가입"><span className="brand-mark" aria-hidden="true">☁</span> SU Cloud <small>셀프서비스 포털</small></a><span className="badge">실제 API 연동 · 개발용</span></header>
    <main>
      <div className="heading"><p className="eyebrow">GET STARTED</p><h1>SU Cloud 회원가입</h1><p className="sub">학교 이메일 인증으로 포털 계정을 만드세요.</p></div>
      <div className={`notice ${notice.error ? 'error-notice' : 'blue-notice'}`} role={notice.error ? 'alert' : 'status'} aria-live="polite">{notice.message}</div>
      <div className="layout"><section className="card signup-card" aria-label="학생 회원가입">
        <ol className="steps"><li className={!user ? 'active' : ''}><span>1</span> 정보 입력 · 이메일 인증</li><li className={user ? 'active' : ''}><span>2</span> 가입 완료</li></ol>
        <div className="content">
          {user && <section className="complete" aria-label="가입 성공"><div className="success-icon" aria-hidden="true">✓</div><h2>회원가입이 완료되었습니다</h2><p>{user.name}님의 포털 계정이 생성되었습니다.</p><dl className="facts"><div><dt>학번</dt><dd>{user.login_id}</dd></div><div><dt>학교 이메일</dt><dd>{user.school_email}</dd></div><div><dt>계정 기본값</dt><dd>{user.account_role} · {user.member_type} · {user.notification_email_type}</dd></div><div><dt>사용자 ID</dt><dd>{user.user_id}</dd></div></dl><p className="helper">로그인·Warpgate 연동은 후속 구현 단계입니다.</p></section>}
          <div className="section-top"><h2>가입 정보</h2><span className="helper">* 필수 입력</span></div>
          <form noValidate onSubmit={(event: FormEvent) => { event.preventDefault(); void perform('signup') }}>
            <div className="fields">
              {field('name', '이름', 'name', '1~40자')}{field('department', '학과', 'organization', '1~100자')}
              {field('login_id', '학번', 'username', '1~32자 · 선행 0을 보존합니다. 이메일 앞부분과 달라도 됩니다.')}
              <div className="field full"><label htmlFor="school_email">학교 이메일<span aria-hidden="true"> *</span></label><div className="email-row"><input id="school_email" name="school_email" type="email" autoComplete="email" autoCapitalize="none" spellCheck={false} value={form.school_email} disabled={busy} onChange={event => edit('school_email', event.target.value)} placeholder="student@syuin.ac.kr" aria-invalid={!!errors.school_email} aria-describedby="email-help email-error" /><button className="btn" type="button" disabled={disabled || cooldown > 0} onClick={() => void perform('issue')}>{cooldown > 0 ? `${cooldown}초 후 재발급` : challenge ? '인증번호 재발급' : '인증번호 받기'}</button></div><p id="email-help" className="helper">@syuin.ac.kr · 앞뒤 공백과 대소문자를 정리하며 점·+태그는 유지합니다.</p><p id="email-error" className="field-error">{errors.school_email}</p>
                {challenge && <div className="email-auth"><label htmlFor="verification_code">이메일 인증번호</label><div className="email-row"><input id="verification_code" inputMode="numeric" autoComplete="one-time-code" value={code} disabled={busy || !sameEmail} onChange={event => setCode(event.target.value)} placeholder="메일의 6자리 번호" /><button className="btn" type="button" disabled={disabled || !sameEmail || codeSeconds <= 0} onClick={() => void perform('verify')}>인증 확인</button></div><p className="helper">{!sameEmail ? '주소가 변경되었습니다. 새 주소로 번호를 다시 받아 주세요.' : verified ? `인증 완료 · 가입 가능 시간 ${duration(grantSeconds)}` : `번호 확인 남은 시간 ${duration(codeSeconds)}`}</p>{grant && grantSeconds <= 0 && <p className="field-error">가입 가능 시간이 만료되었습니다. 다시 인증해 주세요.</p>}</div>}
              </div>
              {field('password', '비밀번호', 'new-password', '8~64자 · 영문·숫자·특수기호 중 2종류 이상')}
              {field('password_confirm', '비밀번호 확인', 'new-password')}
            </div>
            <label className="check"><input type="checkbox" checked={showPassword} onChange={event => setShowPassword(event.target.checked)} />비밀번호 표시</label>
            <div className="form-footer"><button className="btn primary wide" type="submit" disabled={disabled || !verified || !!user}>{busy ? '요청 처리 중…' : '가입하기'}</button><p className="helper">학교 이메일 인증을 완료한 후 가입할 수 있습니다.</p></div>
          </form>
        </div>
      </section>
      <aside>
        <section className="card aside-card"><h2>{mail.title}</h2><p>{mail.description}</p>{mailDelivery === 'file' && <code>.local/mail/*.log</code>}<p className="helper">Django와 Celery 워커가 실행 중이어야 합니다. 발송 요청 접수는 수신함 도착을 보장하지 않습니다.</p><hr /><h3>직접 확인할 수 있어요</h3><ul><li>인증번호 10분 · 재발급 대기 60초</li><li>인증 성공 후 가입 가능 시간</li><li>잘못된 입력·번호·중복 계정 오류</li><li>서버의 실제 HTTP 응답</li></ul><p className="helper">동의 기록 정책은 Warpgate 연동 이후 진행합니다.</p></section>
        <section className="card aside-card"><h2>화면 목업 미리보기</h2><p className="helper">받은 원본 디자인을 읽기 전용으로 표시합니다. 현재 API 연동은 회원가입 화면입니다.</p><div className="preview-links">{Object.entries(previews).map(([key, label]) => <button className="text-button" type="button" key={key} onClick={() => openPreview(key as keyof typeof previews)}>{label} 디자인</button>)}</div></section>
      </aside></div>
      <div className="session-tools"><span className={`badge ${token ? 'connected' : ''}`}>{connecting ? '연결 중' : token ? 'CSRF 연결됨' : '연결 필요'}</span><button className="text-button" type="button" disabled={connecting || busy} onClick={() => void reconnect()}>CSRF 연결 갱신</button><button className="text-button" type="button" disabled={busy} onClick={() => reset(true)}>새 예시 정보</button><button className="text-button" type="button" disabled={busy} onClick={() => reset()}>입력 초기화</button></div>
      {import.meta.env.DEV && <details className="card test-tools"><summary>개발용 API 점검 도구</summary><div className="tool-body"><p>입력 검사를 우회해 요청을 보내고 오류·중복·동시 소비를 확인합니다. 성공한 가입은 실제 개발 DB에 저장됩니다.</p><div className="tool-row"><label>시험할 API<select value={action} onChange={event => { const selected = event.target.value as Action; setAction(selected); prepareDraft(selected) }}><option value="issue">UAPI-01 인증번호 발급</option><option value="verify">UAPI-02 인증 확인</option><option value="signup">UAPI-03 회원가입</option></select></label><button className="btn" type="button" disabled={busy} onClick={() => prepareDraft()}>현재 입력에서 요청 만들기</button></div><label htmlFor="request-json">요청 본문</label><textarea id="request-json" spellCheck={false} value={draft} onChange={event => setDraft(event.target.value)} disabled={busy} /><p className="helper">가입 비밀번호·확인 값은 위 폼에서 가져옵니다. flow_id·challenge_id·주소를 바꾸거나 account_role: ADMIN을 추가해 거절되는지 시험할 수 있습니다.</p><label className="check"><input type="checkbox" checked={omitCsrf} onChange={event => setOmitCsrf(event.target.checked)} disabled={busy} />CSRF 헤더 없이 요청하기</label><div className="tool-buttons"><button className="btn" type="button" disabled={disabled} onClick={() => runTool()}>요청 1회 보내기</button><button className="btn" type="button" disabled={disabled} onClick={() => runTool(2)}>동일 요청 2개 동시 보내기</button></div><p className="helper">번호 만료·재발급 대기·요청 제한은 서버 시각을 따릅니다. DB 롤백·다른 인증 목적·잠금의 세부 검증은 백엔드 자동 테스트를 사용하세요.</p></div></details>}
      <section className="card response-panel" aria-label="실제 API 응답"><h2>실제 API 응답</h2><p className="helper">최근 6개 응답 · 요청 비밀번호와 인증번호는 기록하지 않습니다.</p>{history.length === 0 ? <p className="empty">인증번호 받기를 누르면 서버 응답이 표시됩니다.</p> : history.map((result, index) => <details key={`${result.label}-${index}`} open={index === 0}><summary><span>{result.label}</span><strong className={result.status < 300 ? 'http-ok' : 'http-error'}>HTTP {result.status}</strong></summary><pre>{JSON.stringify(result.body, null, 2)}</pre></details>)}</section>
      <footer>SU Cloud · Phase 1 개발용 연동 화면 · 디자인 검토 중</footer>
    </main>
    <dialog ref={previewDialog} className="preview-dialog" onClose={() => setPreview(null)}><div className="dialog-head"><div><h2>{preview ? previews[preview] : ''} 디자인 미리보기</h2><p className="helper">읽기 전용 · API 미연동 · 예시 계정·자원 표시</p></div><button className="btn" type="button" onClick={() => previewDialog.current?.close()}>닫기</button></div>{preview && <iframe title={`${previews[preview]} 목업`} src={`/mockups/${preview}.html`} sandbox="" />}</dialog>
  </>
}

export default App
