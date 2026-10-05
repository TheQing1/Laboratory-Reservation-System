// 后端接口冒烟测试：覆盖认证、实验室、设备、预约、知识库、AI 助手。
const BASE = process.env.BASE || 'http://127.0.0.1:8000/api';
let pass = 0, fail = 0;
const failures = [];

async function call(method, path, { token, body, raw } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'content-type': 'application/json',
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  if (raw) return { status: res.status, text };
  try {
    return { status: res.status, json: JSON.parse(text) };
  } catch {
    return { status: res.status, text };
  }
}

function check(name, cond, detail = '') {
  if (cond) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; failures.push(name); console.log(`  FAIL  ${name}  ${detail}`); }
}

(async () => {
  console.log('\n=== 1. 健康检查与文档 ===');
  let r = await call('GET', '/health');
  check('健康检查', r.json?.code === 200, JSON.stringify(r.json));

  console.log('\n=== 2. 认证 ===');
  r = await call('POST', '/auth/login', { body: { username: 'admin', password: 'admin123' } });
  check('管理员登录', r.json?.code === 200 && r.json.data?.token, JSON.stringify(r.json).slice(0, 200));
  const adminToken = r.json?.data?.token;

  r = await call('POST', '/auth/login', { body: { username: 'student', password: 'student123' } });
  check('学生登录', r.json?.code === 200 && r.json.data?.token, JSON.stringify(r.json).slice(0, 200));
  const studentToken = r.json?.data?.token;

  r = await call('POST', '/auth/login', { body: { username: 'admin', password: 'wrong' } });
  const wrongCode = r.json?.code;
  check('错误密码被拒绝', wrongCode !== 200, JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/auth/me', { token: studentToken });
  check('获取当前用户', r.json?.data?.username === 'student', JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/auth/me');
  check('未登录被拦截', r.json?.code === 401, JSON.stringify(r.json).slice(0, 200));

  console.log('\n=== 3. 实验室与设备 ===');
  r = await call('GET', '/labs?page=1&page_size=5', { token: studentToken });
  check('实验室列表', r.json?.data?.total >= 8 && r.json.data.list.length === 5,
    `total=${r.json?.data?.total}`);
  const labId = r.json?.data?.list?.[0]?.id;

  r = await call('GET', `/labs/${labId}`, { token: studentToken });
  check('实验室详情含设备', Array.isArray(r.json?.data?.equipments) && r.json.data.equipments.length > 0);

  r = await call('GET', '/labs?keyword=人工智能', { token: studentToken });
  check('实验室关键词搜索', r.json?.data?.total === 1, JSON.stringify(r.json?.data?.list?.map(l => l.name)));

  r = await call('GET', `/labs/${labId}/availability`, { token: studentToken });
  check('空闲时段查询', Array.isArray(r.json?.data?.free_slots), JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/equipments?keyword=示波器', { token: studentToken });
  check('设备搜索', r.json?.data?.total >= 1, JSON.stringify(r.json?.data?.list?.map(e => e.name)));

  r = await call('GET', '/equipments', { token: studentToken });
  check('设备列表', r.json?.data?.total >= 30, `total=${r.json?.data?.total}`);

  console.log('\n=== 4. 权限控制 ===');
  r = await call('POST', '/labs', { token: studentToken, body: { name: '非法实验室', capacity: 5 } });
  check('学生不能建实验室', r.json?.code === 403, JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/users', { token: studentToken });
  check('学生不能看用户列表', r.json?.code === 403, JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/users', { token: adminToken });
  check('管理员可看用户列表', r.json?.data?.total >= 6, JSON.stringify(r.json).slice(0, 200));

  console.log('\n=== 5. 预约业务 ===');
  const tmr = new Date(Date.now() + 86400000).toISOString().slice(0, 10);

  // 先清掉本测试可能残留的预约，保证可重复执行
  r = await call('GET', '/reservations?page_size=100', { token: adminToken });
  for (const item of r.json?.data?.list || []) {
    if (/冒烟测试|冲突预约|AI 助手代提交/.test(item.purpose || '')) {
      await call('DELETE', `/reservations/${item.id}`, { token: adminToken });
    }
  }

  // 取实验室当天的真实空闲时段，避免与演示数据撞车
  r = await call('GET', `/labs/3/availability?date=${tmr}`, { token: studentToken });
  const freeSlots = r.json?.data?.free_slots || [];
  const slot = freeSlots.find(s => s.start >= '09:00' && s.end <= '18:00') || freeSlots[0];
  check('可获取空闲时段用于预约', !!slot, JSON.stringify(freeSlots.slice(0, 3)));

  r = await call('POST', '/reservations', {
    token: studentToken,
    body: { lab_id: 3, booking_date: tmr, start_time: slot.start, end_time: slot.end, purpose: '冒烟测试预约', people_count: 5 },
  });
  check('提交预约', r.json?.code === 200 && r.json.data?.id, JSON.stringify(r.json).slice(0, 300));
  const resId = r.json?.data?.id;

  r = await call('POST', '/reservations', {
    token: studentToken,
    body: { lab_id: 3, booking_date: tmr, start_time: slot.start, end_time: slot.end, purpose: '冲突预约', people_count: 5 },
  });
  check('时间冲突被拦截', r.json?.code !== 200 && /冲突/.test(r.json?.message || ''), JSON.stringify(r.json).slice(0, 300));

  r = await call('POST', '/reservations', {
    token: studentToken,
    body: { lab_id: 3, booking_date: tmr, start_time: '23:00', end_time: '23:30', purpose: '超出开放时间', people_count: 5 },
  });
  check('超出开放时间被拦截', r.json?.code !== 200, JSON.stringify(r.json).slice(0, 200));

  r = await call('POST', '/reservations', {
    token: studentToken,
    body: { lab_id: 3, booking_date: '2020-01-01', start_time: '09:00', end_time: '10:00', purpose: '过去日期', people_count: 5 },
  });
  check('过去日期被拦截', r.json?.code !== 200, JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/reservations?mine=true', { token: studentToken });
  check('我的预约列表', r.json?.data?.total >= 1, JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/reservations', { token: adminToken });
  check('管理员预约列表', r.json?.data?.total >= 12, `total=${r.json?.data?.total}`);

  r = await call('PUT', `/reservations/${resId}/review`, {
    token: adminToken, body: { status: 'approved', review_remark: '冒烟测试通过' },
  });
  check('管理员审核通过', r.json?.data?.status === 'approved', JSON.stringify(r.json).slice(0, 300));

  r = await call('PUT', `/reservations/${resId}/review`, {
    token: adminToken, body: { status: 'approved' },
  });
  check('重复审核被拦截', r.json?.code !== 200, JSON.stringify(r.json).slice(0, 200));

  r = await call('GET', '/reservations/stats', { token: studentToken });
  check('预约统计', typeof r.json?.data?.total === 'number', JSON.stringify(r.json).slice(0, 200));

  console.log('\n=== 5b. 并发抢约（30 分钟槽位唯一约束）===');
  r = await call('GET', `/labs/4/availability?date=${tmr}`, { token: studentToken });
  const concSlot = (r.json?.data?.free_slots || []).find(s => s.start >= '09:00' && s.end <= '17:00');
  let concSuccess = 0;
  let concFail = 0;
  if (concSlot) {
    // 8 个请求同时抢同一个时段：正确实现下只允许 1 单成功
    const results = await Promise.all(
      Array.from({ length: 8 }, (_, i) =>
        call('POST', '/reservations', {
          token: studentToken,
          body: {
            lab_id: 4, booking_date: tmr,
            start_time: concSlot.start, end_time: concSlot.end,
            purpose: `冒烟测试并发预约-${i}`, people_count: 4,
          },
        })
      )
    );
    concSuccess = results.filter((x) => x.json?.code === 200).length;
    concFail = results.length - concSuccess;
  }
  check('并发抢同一时段恰好成功 1 单', !!concSlot && concSuccess === 1,
    `success=${concSuccess} fail=${concFail} slot=${concSlot?.start}-${concSlot?.end}`);

  console.log('\n=== 6. 仪表盘 ===');
  r = await call('GET', '/dashboard/stats', { token: adminToken });
  const ds = r.json?.data;
  check('概览统计', ds?.total_labs >= 8 && Array.isArray(ds?.trend) && ds.trend.length === 7,
    JSON.stringify(ds).slice(0, 300));
  check('推荐实验室', Array.isArray(ds?.recommended) && ds.recommended.length > 0);
  check('状态分布', Array.isArray(ds?.status_distribution));

  r = await call('GET', '/dashboard/stats', { token: studentToken });
  check('学生端个人统计', typeof r.json?.data?.my_total === 'number');

  console.log('\n=== 7. 知识库 / RAG ===');
  r = await call('GET', '/documents', { token: adminToken });
  check('文档列表', r.json?.data?.total >= 11, `total=${r.json?.data?.total}`);

  r = await call('GET', '/documents/stats', { token: adminToken });
  check('知识库统计', r.json?.data?.chunks >= 11, JSON.stringify(r.json?.data));

  r = await call('POST', '/documents/search?query=' + encodeURIComponent('实验室违规怎么处理') + '&top_k=3', { token: studentToken });
  const hits = r.json?.data || [];
  check('RAG 检索命中违规规定', hits.length > 0 && /违规|扣|暂停/.test(JSON.stringify(hits)),
    JSON.stringify(hits).slice(0, 300));

  r = await call('POST', '/documents/search?query=' + encodeURIComponent('GPU服务器怎么用') + '&top_k=3', { token: studentToken });
  check('RAG 检索 GPU 说明', (r.json?.data || []).length > 0, JSON.stringify(r.json?.data).slice(0, 300));

  console.log('\n=== 8. AI 助手（本地引擎）===');
  r = await call('POST', '/chat', { token: studentToken, body: { message: '有哪些实验室可以预约？' } });
  check('实验室咨询', r.json?.code === 200 && /实验室/.test(r.json?.data?.reply || ''),
    (r.json?.data?.reply || '').slice(0, 130));
  check('过程可见（steps）', Array.isArray(r.json?.data?.steps) && r.json.data.steps.length > 0);

  r = await call('POST', '/chat', { token: studentToken, body: { message: 'GPU服务器在哪里？有几台？' } });
  check('设备咨询', /GPU|A100|人工智能/.test(r.json?.data?.reply || ''), (r.json?.data?.reply || '').slice(0, 130));

  r = await call('POST', '/chat', { token: studentToken, body: { message: '人工智能实验室有哪些设备？' } });
  check('按实验室查设备清单', /GPU|工作站|交换机|智慧屏/.test(r.json?.data?.reply || ''),
    (r.json?.data?.reply || '').slice(0, 130));

  r = await call('POST', '/chat', { token: studentToken, body: { message: '显微镜在哪个实验室？' } });
  check('设备模糊匹配', /显微镜|生物医学/.test(r.json?.data?.reply || ''), (r.json?.data?.reply || '').slice(0, 130));

  r = await call('POST', '/chat', { token: studentToken, body: { message: '实验室安全规定有哪些？' } });
  check('知识库问答', /安全|实验服|试剂/.test(r.json?.data?.reply || ''), (r.json?.data?.reply || '').slice(0, 130));

  r = await call('POST', '/chat', { token: studentToken, body: { message: '人工智能实验室明天有空吗' } });
  check('空闲时段咨询', /空闲|时段|约满/.test(r.json?.data?.reply || ''), (r.json?.data?.reply || '').slice(0, 130));

  r = await call('POST', '/chat', { token: studentToken, body: { message: '我的预约记录' } });
  check('我的预约咨询', /预约/.test(r.json?.data?.reply || ''), (r.json?.data?.reply || '').slice(0, 130));

  const d3 = new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10);
  r = await call('GET', `/labs/6/availability?date=${d3}`, { token: studentToken });
  const aiSlot = (r.json?.data?.free_slots || []).find(s => s.start >= '10:00' && s.end <= '17:00');
  let aiReply = '';
  if (aiSlot) {
    r = await call('POST', '/chat', {
      token: studentToken,
      body: { message: `帮我预约电子电工实验室 ${d3} ${aiSlot.start}-${aiSlot.end} 用于电路实验，6个人` },
    });
    aiReply = r.json?.data?.reply || '';
  }
  check('AI 代提交预约', /已提交|没有提交成功|请补充/.test(aiReply), aiReply.slice(0, 200));

  r = await call('GET', '/chat/sessions', { token: studentToken });
  check('会话列表', Array.isArray(r.json?.data) && r.json.data.length >= 1, JSON.stringify(r.json?.data).slice(0, 200));

  console.log('\n=== 9. SSE 流式输出 ===');
  const sseRes = await fetch(BASE + '/chat/stream', {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${studentToken}` },
    body: JSON.stringify({ message: '介绍一下人工智能实验室' }),
  });
  const sseText = await sseRes.text();
  const events = sseText.split('\n\n').filter(l => l.startsWith('data: ')).map(l => l.slice(6));
  const types = events.map(e => { try { return JSON.parse(e).type; } catch { return 'DONE'; } });
  check('SSE 状态码 200', sseRes.status === 200, String(sseRes.status));
  check('SSE content-type', (sseRes.headers.get('content-type') || '').includes('text/event-stream'));
  check('SSE 包含 start', types.includes('start'), types.join(','));
  check('SSE 包含 delta 增量', types.filter(t => t === 'delta').length > 0, `delta=${types.filter(t => t === 'delta').length}`);
  check('SSE 包含 done', types.includes('done'), types.join(','));

  console.log('\n=== 10. 新增/修改/删除闭环 ===');
  r = await call('POST', '/labs', {
    token: adminToken,
    body: { name: '冒烟测试实验室', code: 'TMP-001', building: '测试楼', room: '101', capacity: 10, open_time: '09:00', close_time: '17:00' },
  });
  check('管理员新增实验室', r.json?.code === 200 && r.json.data?.id, JSON.stringify(r.json).slice(0, 200));
  const tmpLabId = r.json?.data?.id;

  r = await call('POST', '/labs', { token: adminToken, body: { name: '冒烟测试实验室', capacity: 10 } });
  check('重名实验室被拦截', r.json?.code === 409, JSON.stringify(r.json).slice(0, 200));

  r = await call('PUT', `/labs/${tmpLabId}`, { token: adminToken, body: { capacity: 20, status: 'maintenance' } });
  check('修改实验室', r.json?.data?.capacity === 20 && r.json?.data?.status === 'maintenance');

  r = await call('POST', '/equipments', { token: adminToken, body: { lab_id: tmpLabId, name: '测试设备', quantity: 3, status: 'normal' } });
  check('新增设备', r.json?.code === 200 && r.json.data?.id, JSON.stringify(r.json).slice(0, 200));
  const tmpEqId = r.json?.data?.id;

  r = await call('DELETE', `/equipments/${tmpEqId}`, { token: adminToken });
  check('删除设备', r.json?.code === 200);

  r = await call('DELETE', `/labs/${tmpLabId}`, { token: adminToken });
  check('删除实验室', r.json?.code === 200, JSON.stringify(r.json).slice(0, 200));

  r = await call('POST', '/documents', {
    token: adminToken,
    body: { title: '冒烟测试文档', category: '测试', content: '这是一篇用于验证向量化的测试文档，内容涉及实验室预约流程与安全须知。' },
  });
  check('新增知识文档并向量化', r.json?.data?.chunks >= 1, JSON.stringify(r.json).slice(0, 200));
  const tmpDocId = r.json?.data?.id;
  r = await call('DELETE', `/documents/${tmpDocId}`, { token: adminToken });
  check('删除知识文档', r.json?.code === 200);

  // 先记录原资料，测试后还原，避免污染演示数据
  const meBefore = await call('GET', '/auth/me', { token: studentToken });
  const origin = meBefore.json?.data || {};
  r = await call('PUT', '/users/profile/me', { token: studentToken, body: { name: '张同学', college: '计算机学院', phone: '13900000009' } });
  check('修改个人资料', r.json?.data?.phone === '13900000009', JSON.stringify(r.json).slice(0, 200));
  await call('PUT', '/users/profile/me', {
    token: studentToken,
    body: { name: origin.name ?? '', college: origin.college ?? '', phone: origin.phone ?? '' },
  });

  r = await call('PUT', '/users/password/me', { token: studentToken, body: { old_password: 'wrong', new_password: 'newpass123' } });
  check('错误原密码被拦截', r.json?.code !== 200);

  r = await call('POST', '/reservations', { token: 'invalid.token.here', body: { lab_id: 1, booking_date: tmr, start_time: '09:00', end_time: '10:00' } });
  check('无效 token 被拦截', r.json?.code === 401, JSON.stringify(r.json).slice(0, 200));

  console.log('\n' + '='.repeat(56));
  console.log(`结果：通过 ${pass} 项，失败 ${fail} 项`);
  if (failures.length) console.log('失败项：\n - ' + failures.join('\n - '));
  console.log('='.repeat(56));
  process.exit(fail ? 1 : 0);
})();
