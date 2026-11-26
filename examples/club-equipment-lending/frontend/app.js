const byId = (id) => document.getElementById(id);
const screens = ['session', 'login', 'register', 'register-success', 'equipment', 'availability', 'management',
  'requests', 'request-new', 'request-detail'];
const device = byId('device');
const fromInput = byId('from');
const toInput = byId('to');
const clubOffset = '+07:00';
const clubTime = {
  timeZone: clubOffset,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
};
const minuteFormat = new Intl.DateTimeFormat('vi-VN', clubTime);
const secondFormat = new Intl.DateTimeFormat('vi-VN', { ...clubTime, second: '2-digit' });
let user = null;
let catalogRequest;
let availabilityRequest;
let checkingSession = false;
let sessionVerification;
let loggingOut = false;
let loanView;
let loanLoginRoute;
let registrationRequest;
let registrationRetryAt = 0;
let registrationTimer;

class ApiError extends Error {
  constructor(response, code) {
    super(code);
    this.status = response.status;
    this.retryAfter = Number(response.headers.get('Retry-After'));
  }
}

async function api(path, options) {
  const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options });
  if (response.status === 204) return;
  if (response.ok) return response.json();
  const body = await response.json().catch(() => null);
  throw new ApiError(response, body?.code);
}

function message(id, text, error = false) {
  const node = byId(id);
  node.textContent = text;
  node.classList.toggle('error', error);
}

function show(screen) {
  if (screen !== 'register' && byId('register').hidden === false) resetRegistration();
  if (screen !== 'register-success') byId('created-name').textContent = '';
  loanView?.abort();
  managementView?.read?.abort();
  for (const [id, decision] of managementDecisions) {
    if (decision.blockedView && decision.blockedView === managementView) managementDecisions.delete(id);
  }
  managementView = undefined;
  decisionDialog.close();
  byId('management-rows').replaceChildren();
  byId('request-rows').replaceChildren();
  byId('request-data').hidden = true;
  for (const id of ['detail-device', 'detail-created', 'detail-start', 'detail-end', 'request-badge']) {
    byId(id).textContent = '';
  }
  byId('request-form').reset();
  byId('request-device').replaceChildren();
  catalogRequest?.abort();
  clearAvailability();
  byId('lookup').reset();
  device.replaceChildren();
  byId('lookup-fields').disabled = true;
  byId('app-panel').classList.toggle('panel-wide', ['availability', 'management'].includes(screen));
  byId('assets').replaceChildren();
  byId('assets').hidden = true;
  for (const id of screens) byId(id).hidden = id !== screen;

  const manager = user?.role === 'MANAGER';
  byId('role').textContent = user ? (manager ? 'Quản lý' : 'Thành viên') : '';
  byId('logout').hidden = !user;
  byId('equipment-link').hidden = !user;
  byId('management-link').hidden = !manager;
  byId('approved-link').hidden = !manager;
  byId('handed-over-link').hidden = !manager;
  byId('requests-link').hidden = user?.role !== 'MEMBER';
  for (const id of ['equipment', 'management', 'requests']) {
    const link = byId(id + '-link');
    if ((id === screen && (id !== 'management' || managementListRoute(location.hash) === '#management'))
      || (id === 'equipment' && screen === 'availability')) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  for (const [route, id] of [[approvedRoute, 'approved-link'], [handedOverRoute, 'handed-over-link']]) {
    const link = byId(id);
    if (screen === 'management' && managementListRoute(location.hash) === route) {
      link.setAttribute('aria-current', 'page');
    } else link.removeAttribute('aria-current');
  }
  byId(screen + '-title').focus();
}

function endSession(text = '') {
  user = null;
  managementDecisions.clear();
  history.replaceState(null, '', '#login');
  byId('password').value = '';
  message('action-status', '');
  show('login');
  message('login-status', text, Boolean(text));
}

function expired() {
  if (isManagementRoute(location.hash)) loanLoginRoute = location.hash;
  endSession('Phiên đã hết hạn. Vui lòng đăng nhập lại.');
}

async function loadCatalog(selectedId) {
  catalogRequest?.abort();
  const request = new AbortController();
  catalogRequest = request;
  const forLookup = selectedId !== undefined;
  const statusId = forLookup ? 'lookup-catalog-status' : 'catalog-status';
  const retry = byId(forLookup ? 'lookup-catalog-retry' : 'retry');
  retry.hidden = true;
  message(statusId, 'Đang tải danh mục…');

  try {
    const equipment = await api('/equipment', { signal: request.signal });
    if (request.signal.aborted) return;
    if (forLookup) {
      const options = equipment.map(({ id, name, asset_code }) => new Option(name + ' · ' + asset_code, id));
      device.replaceChildren(...options);
      device.value = selectedId;
      const missing = options.length > 0 && device.selectedIndex < 0;
      if (missing) {
        const placeholder = new Option('Chọn thiết bị', '');
        placeholder.disabled = true;
        device.prepend(placeholder);
        device.value = '';
      }
      byId('lookup-fields').disabled = options.length === 0;
      message(statusId, options.length === 0 ? 'Chưa có thiết bị để tra cứu.'
        : missing ? 'Thiết bị đã chọn không còn khả dụng. Hãy chọn thiết bị trong danh mục.' : '');
      return;
    }
    const rows = equipment.map(({ id, asset_code, name }) => {
      const item = document.createElement('li');
      item.className = 'asset';
      item.dataset.equipmentId = id;
      const title = document.createElement('strong');
      title.textContent = name;
      const details = document.createElement('div');
      details.append(title, document.createElement('br'), asset_code);
      const link = document.createElement('a');
      link.href = '#availability/' + encodeURIComponent(id);
      link.textContent = 'Xem lịch';
      link.setAttribute('aria-label', 'Xem lịch · ' + name + ' · ' + asset_code);
      item.append(details, link);
      return item;
    });
    byId('assets').replaceChildren(...rows);
    byId('assets').hidden = rows.length === 0;
    message(statusId, rows.length ? '' : 'Chưa có thiết bị để tra cứu.');
  } catch (error) {
    if (request.signal.aborted) return;
    if (error.status === 401) return expired();
    if (error.status === 403) return message(statusId, 'Bạn không có quyền truy cập.', true);
    message(statusId, 'Không tải được danh mục.', true);
    retry.hidden = false;
  }
}

function fieldError(input, text = '') {
  message(input.id + '-error', text, Boolean(text));
  input.setAttribute('aria-invalid', String(Boolean(text)));
}

function resetRegistration() {
  registrationRequest?.abort();
  registrationRequest = undefined;
  clearTimeout(registrationTimer);
  byId('register-form').reset();
  byId('register-fields').disabled = false;
  fieldError(byId('register-name'));
  fieldError(byId('register-password'));
  message('register-status', '');
  message('register-error', '');
}

function updateRegistrationRetry() {
  const seconds = Math.ceil((registrationRetryAt - Date.now()) / 1000);
  byId('register-submit').disabled = seconds > 0;
  if (seconds <= 0) {
    if (registrationRetryAt) message('register-status', 'Bạn có thể gửi lại.');
    registrationRetryAt = 0;
    return;
  }
  message('register-status', 'Quá nhiều lượt đăng ký. Hãy thử lại sau ' + seconds + ' giây.');
  registrationTimer = setTimeout(updateRegistrationRetry, 1000);
}

function showRegistration() {
  byId('password').value = '';
  message('login-status', '');
  show('register');
  clearTimeout(registrationTimer);
  if (!registrationRequest) updateRegistrationRetry();
}

function registrationPasswordError(password) {
  if (!password) return 'Vui lòng nhập mật khẩu.';
  const codePoints = [...password];
  if (codePoints.some(point => /^[\uD800-\uDFFF]$/.test(point))) {
    return 'Mật khẩu chứa ký tự Unicode không hợp lệ.';
  }
  if (!password.trim()) return 'Mật khẩu phải có ít nhất một ký tự khác khoảng trắng.';
  if (codePoints.length < 8) return 'Mật khẩu phải có ít nhất 8 ký tự';
  if (new TextEncoder().encode(password).length > 1024) return 'Mật khẩu vượt quá 1.024 byte UTF-8.';
  return '';
}

async function submitRegistration(event) {
  event.preventDefault();
  const submit = byId('register-submit');
  if (byId('register').hidden || location.hash !== '#register' || submit.disabled) return;

  const nameInput = byId('register-name');
  const passwordInput = byId('register-password');
  const username = nameInput.value;
  const password = passwordInput.value;
  const nameError = !username.trim() ? 'Vui lòng nhập tên đăng nhập.'
    : username.length > 128 || !/^[a-z0-9][a-z0-9._-]{2,63}$/.test(username.trim().toLowerCase())
      ? 'Tên đăng nhập chưa đúng định dạng.' : '';
  const passwordError = registrationPasswordError(password);
  fieldError(nameInput, nameError);
  fieldError(passwordInput, passwordError);
  message('register-error', '');
  if (nameError || passwordError) {
    (nameError ? nameInput : passwordInput).focus();
    return;
  }

  const request = new AbortController();
  registrationRequest = request;
  const fields = byId('register-fields');
  fields.disabled = true;
  submit.disabled = true;
  message('register-status', 'Đang tạo tài khoản…');
  let focusName = false;
  try {
    const created = await api('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(15000)]),
    });
    if (request.signal.aborted || location.hash !== '#register') return;
    byId('username').value = created.username;
    byId('password').value = '';
    byId('created-name').textContent = created.username;
    loanLoginRoute = undefined;
    history.replaceState(null, '', '#register/success');
    show('register-success');
  } catch (error) {
    if (request.signal.aborted || location.hash !== '#register') return;
    switch (error.message) {
      case 'INVALID_INPUT':
        message('register-error', 'Thông tin đăng ký chưa hợp lệ. Hãy kiểm tra và thử lại.', true);
        break;
      case 'ORIGIN_FORBIDDEN':
        message('register-error', 'Không thể gửi đăng ký từ trang này. Hãy mở lại trang đăng nhập của CLB.', true);
        break;
      case 'USERNAME_TAKEN':
        fieldError(nameInput, 'Tên đăng nhập đã được sử dụng.');
        focusName = true;
        break;
      case 'REGISTER_RATE_LIMITED':
        registrationRetryAt = Date.now() + 1000 * (error.retryAfter > 0 ? error.retryAfter : 60);
        break;
      default:
        message('register-error', error instanceof TypeError || error.name === 'TimeoutError'
          ? 'Chưa xác định tài khoản đã được tạo. Bạn có thể thử đăng nhập hoặc gửi lại.'
          : 'Chưa thể tạo tài khoản. Hãy thử lại.', true);
    }
  } finally {
    if (registrationRequest === request) {
      registrationRequest = undefined;
      fields.disabled = false;
      message('register-status', '');
      updateRegistrationRetry();
      if (focusName) nameInput.focus();
    }
  }
}

function clearAvailability(text = '') {
  availabilityRequest?.abort();
  for (const id of ['lookup-context', 'lookup-updated', 'slots']) byId(id).replaceChildren();
  for (const id of ['slots', 'lookup-retry', 'reload-catalog']) byId(id).hidden = true;
  for (const input of [device, fromInput, toInput]) fieldError(input);
  message('lookup-status', text);
}

function toClubInstant(input) {
  if (!input.validity.valid || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(input.value)) return;
  const instant = new Date(input.value + ':00' + clubOffset);
  if (instant.getUTCFullYear() >= 1 && instant.getUTCFullYear() <= 9999) return instant;
}

function formatClubTime(value) {
  const instant = new Date(value);
  const millis = instant.getUTCMilliseconds();
  if (millis) {
    const fraction = String(millis).padStart(3, '0');
    return secondFormat.formatToParts(instant).map(({ type, value }) =>
      type === 'second' ? value + ',' + fraction : value).join('');
  }
  return (instant.getUTCSeconds() ? secondFormat : minuteFormat).format(instant);
}

async function lookupAvailability(event) {
  event.preventDefault();
  if (byId('lookup-fields').disabled || byId('availability').hidden) return;
  clearAvailability();
  const from = toClubInstant(fromInput);
  const to = toClubInstant(toInput);
  fieldError(device, device.value ? '' : 'Chọn thiết bị để tra cứu.');
  fieldError(fromInput, from ? '' : 'Nhập ngày giờ bắt đầu hợp lệ.');
  fieldError(toInput, !to ? 'Nhập ngày giờ kết thúc hợp lệ.'
    : to <= from ? 'Giờ kết thúc phải sau giờ bắt đầu.' : '');
  const invalid = byId('lookup').querySelector('[aria-invalid="true"]');
  if (invalid) {
    invalid.focus();
    return;
  }

  const request = new AbortController();
  availabilityRequest = request;
  const query = new URLSearchParams({ from: from.toISOString(), to: to.toISOString() });
  const selected = device.selectedOptions[0];
  message('lookup-status', 'Đang tải lịch…');
  try {
    const { as_of, available } = await api('/equipment/' + encodeURIComponent(selected.value)
      + '/availability?' + query, { signal: request.signal });
    if (request.signal.aborted) return;
    const rows = available.map(({ start_at, end_at }) => {
      const row = document.createElement('li');
      row.append(formatClubTime(start_at) + ' → ' + formatClubTime(end_at));
      if (user.role === 'MEMBER') {
        const link = document.createElement('a');
        link.href = '#request/new?' + new URLSearchParams({ equipment_id: selected.value, start_at, end_at });
        link.textContent = 'Gửi yêu cầu';
        row.append(link);
      }
      return row;
    });
    const updated = formatClubTime(as_of);
    message('lookup-context', selected.text + ' · ' + formatClubTime(from) + ' → ' + formatClubTime(to));
    byId('slots').replaceChildren(...rows);
    byId('slots').hidden = rows.length === 0;
    message('lookup-status', rows.length ? '' : 'Không có khung giờ trống trong khoảng đã chọn.');
    message('lookup-updated', 'Cập nhật lúc ' + updated);
  } catch (error) {
    if (request.signal.aborted) return;
    switch (error.status) {
      case 400:
        return message('lookup-status', 'Kiểm tra thiết bị và ngày giờ đã nhập.', true);
      case 401:
        return expired();
      case 403:
        return message('lookup-status', 'Tài khoản thiếu quyền xem lịch.', true);
      case 404:
        byId('reload-catalog').hidden = false;
        return message('lookup-status', 'Thiết bị không còn khả dụng.', true);
      default:
        byId('lookup-retry').hidden = false;
        message('lookup-status', 'Chưa tải được lịch. Hãy thử lại.', true);
    }
  }
}

const loanLabels = {
  PENDING: 'Chờ duyệt',
  APPROVED: 'Đã duyệt',
  REJECTED: 'Đã từ chối',
  HANDED_OVER: 'Đã giao',
  RETURNED: 'Đã trả',
};
const loanDevice = byId('request-device');
const loanStart = byId('request-start');
const loanEnd = byId('request-end');

function showLoanScreen(confirmedId) {
  const [path, query] = location.hash.split('?');
  const screen = path === '#requests' ? 'requests' : path === '#request/new' ? 'request-new' : 'request-detail';
  show(screen);
  const view = new AbortController();
  loanView = view;
  const member = user.role === 'MEMBER';
  byId('new-request-link').hidden = !member;
  byId('request-badge').hidden = true;
  byId('request-detail-title').textContent = 'Chi tiết yêu cầu';
  byId('request-form').hidden = true;
  byId('request-catalog-retry').hidden = true;
  for (const retry of document.querySelectorAll('[data-request-retry]')) retry.hidden = true;
  const confirmation = byId('request-confirmation');
  confirmation.hidden = true;
  message('request-confirmation', '');
  const statusId = screen === 'request-new' ? 'request-catalog-status' : screen + '-status';
  message(statusId, '');
  if (!member) return message(statusId, 'Bạn không có quyền truy cập.', true);

  if (screen === 'request-new') {
    const params = new URLSearchParams(query);
    for (const [field, key] of [[loanStart, 'start_at'], [loanEnd, 'end_at']]) {
      const utc = params.get(key);
      if (utc && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(utc)) {
        const clubLocal = new Date(Date.parse(utc) + 7 * 60 * 60 * 1000);
        if (clubLocal.getUTCFullYear() >= 1 && clubLocal.getUTCFullYear() <= 9999) {
          field.value = clubLocal.toISOString().slice(0, -1);
        }
      }
    }
    for (const field of [loanDevice, loanStart, loanEnd]) fieldError(field);
    message('request-submit-status', '');
    byId('request-form').hidden = false;
    void loadLoanCatalog(view, params.get('equipment_id') || '');
    return;
  }

  const id = /^#request\/(\d+)$/.exec(path)?.[1];
  if (screen === 'request-detail' && !(Number(id) > 0 && Number(id) <= 2147483647)) {
    return message(statusId, 'Không tìm thấy yêu cầu.', true);
  }
  if (confirmedId === Number(id)) {
    confirmation.hidden = false;
    message('request-confirmation', 'Đã gửi yêu cầu.');
  }
  const retry = byId(screen).querySelector('[data-request-retry]');
  retry.onclick = () => {
    byId(screen + '-title').focus();
    void loadLoans(view, screen, id);
  };
  void loadLoans(view, screen, id);
}

async function loadLoans(view, screen, id) {
  const statusId = screen + '-status';
  const { signal } = view;
  const retry = byId(screen).querySelector('[data-request-retry]');
  retry.hidden = true;
  message(statusId, 'Đang tải yêu cầu…');
  try {
    const result = await api(id ? '/loan-requests/' + Number(id) : '/loan-requests', { signal });
    if (signal.aborted) return;
    if (!id && result.length === 0) return message(statusId, 'Bạn chưa có yêu cầu nào.');
    const catalog = await api('/equipment', { signal }).catch(error => {
      if (error.status === 401) throw error;
      return [];
    });
    if (signal.aborted) return;
    const names = new Map(catalog.map(({ id, name, asset_code }) => [id, name + ' · ' + asset_code]));
    const deviceName = item => names.get(item.equipment_id) || 'Thiết bị #' + item.equipment_id;
    if (id) {
      byId('request-detail-title').textContent = 'Yêu cầu #' + result.id;
      const badge = byId('request-badge');
      badge.textContent = loanLabels[result.status];
      badge.hidden = false;
      message('detail-device', deviceName(result));
      message('detail-created', formatClubTime(result.created_at));
      message('detail-start', formatClubTime(result.start_at));
      message('detail-end', formatClubTime(result.end_at));
      byId('request-data').hidden = false;
      return message(statusId, '');
    }
    const rows = result.map(item => {
      const row = document.createElement('li');
      row.className = 'asset';
      const cell = document.createElement('div');
      const link = document.createElement('a');
      link.href = '#request/' + item.id;
      link.textContent = '#' + item.id + ' · ' + deviceName(item);
      const times = document.createElement('div');
      times.className = 'muted';
      times.textContent = formatClubTime(item.start_at) + ' – ' + formatClubTime(item.end_at);
      cell.append(link, times);
      const badge = document.createElement('span');
      badge.className = 'request-badge';
      badge.textContent = loanLabels[item.status];
      row.append(cell, badge);
      return row;
    });
    byId('request-rows').replaceChildren(...rows);
    message(statusId, '');
  } catch (error) {
    if (signal.aborted) return;
    if (error.status === 401) return expired();
    if (error.status === 403) return message(statusId, 'Bạn không có quyền truy cập.', true);
    if (id && error.status === 404) return message(statusId, 'Không tìm thấy yêu cầu.', true);
    message(statusId, 'Không tải được yêu cầu. Hãy thử lại.', true);
    retry.hidden = false;
  }
}

async function loadLoanCatalog(view, selectedId, missing = false) {
  const fields = byId('request-fields');
  const retry = byId('request-catalog-retry');
  const statusId = 'request-catalog-status';
  fields.disabled = true;
  retry.hidden = true;
  message(statusId, 'Đang tải danh mục…');
  try {
    const catalog = await api('/equipment', { signal: view.signal });
    if (view.signal.aborted) return;
    const placeholder = new Option('Chọn thiết bị', '');
    placeholder.disabled = true;
    loanDevice.replaceChildren(placeholder,
      ...catalog.map(({ id, name, asset_code }) => new Option(name + ' · ' + asset_code, id)));
    const available = catalog.some(item => String(item.id) === selectedId);
    loanDevice.value = available ? selectedId : '';
    fields.disabled = catalog.length === 0;
    message(statusId, catalog.length ? '' : 'Chưa có thiết bị để chọn.');
    if (missing || (selectedId && !available)) {
      fieldError(loanDevice, 'Thiết bị không còn khả dụng. Hãy chọn lại.');
      if (!fields.disabled) loanDevice.focus();
    }
  } catch (error) {
    if (view.signal.aborted) return;
    if (error.status === 401) return expired();
    if (error.status === 403) return message(statusId, 'Bạn không có quyền truy cập.', true);
    message(statusId, 'Không tải được danh mục. Hãy thử lại.', true);
    retry.hidden = false;
  }
}

function loanInstant(input) {
  const value = input.value;
  if (!input.validity.valid || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?$/.test(value)) return;
  const instant = new Date(value + clubOffset);
  if (instant.getUTCFullYear() >= 1 && instant.getUTCFullYear() <= 9999) return instant;
}

async function submitLoan(event) {
  event.preventDefault();
  const fields = byId('request-fields');
  if (fields.disabled || loggingOut || byId('request-new').hidden || user?.role !== 'MEMBER') return;
  const statusId = 'request-submit-status';
  message(statusId, '');
  const start = loanInstant(loanStart);
  const end = loanInstant(loanEnd);
  fieldError(loanDevice, loanDevice.value ? '' : 'Chọn thiết bị.');
  fieldError(loanStart, start ? '' : 'Nhập ngày giờ bắt đầu hợp lệ.');
  fieldError(loanEnd, !end ? 'Nhập ngày giờ kết thúc hợp lệ.'
    : start && end <= start ? 'Giờ kết thúc phải sau giờ bắt đầu.' : '');
  const invalid = fields.querySelector('[aria-invalid="true"]');
  if (invalid) return invalid.focus();

  const view = loanView;
  const route = location.hash;
  const data = { equipment_id: Number(loanDevice.value), start_at: start.toISOString(), end_at: end.toISOString() };
  fields.disabled = true;
  message(statusId, 'Đang gửi…');
  try {
    const created = await api('/loan-requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': user.csrf_token },
      body: JSON.stringify(data),
    });
    if (view.signal.aborted || route !== location.hash) return;
    history.pushState(null, '', '#request/' + created.id);
    showLoanScreen(created.id);
  } catch (error) {
    if (view.signal.aborted || route !== location.hash) return;
    fields.disabled = false;
    if (error.status === 401) return expired();
    if (error.status === 404) {
      message(statusId, '');
      loanDevice.value = '';
      fieldError(loanDevice, 'Thiết bị không còn khả dụng. Hãy chọn lại.');
      return loadLoanCatalog(view, '', true);
    }
    if (error.status === 400) return message(statusId, 'Vui lòng kiểm tra thiết bị và khoảng giờ.', true);
    if (error.message === 'CSRF_INVALID') {
      return message(statusId, 'Mã xác thực phiên không hợp lệ. Hãy tải lại trang trước khi gửi lại.', true);
    }
    if (error.status === 403) return message(statusId, 'Bạn không có quyền gửi yêu cầu.', true);
    message(statusId, 'Chưa xác nhận được kết quả. Hãy kiểm tra danh sách trước khi gửi lại.', true);
  }
}

let managementView;
const managementDecisions = new Map();
const decisionDialog = byId('decision-dialog');
let decisionSelection;
const approvedRoute = '#management/approved';
const handedOverRoute = '#management/handed-over';

function managementListRoute(hash) {
  return [approvedRoute, handedOverRoute].find((route) => hash === route || hash.startsWith(route + '/'))
    || '#management';
}

function managementListPath(view) {
  if (view.handedOver) return '/loan-requests?status=HANDED_OVER';
  return '/loan-requests' + (view.approved ? '?status=APPROVED' : '');
}

function managementListLabel(view) {
  if (view.handedOver) return 'Đã giao';
  return view.approved ? 'Đã duyệt' : 'Đang chờ';
}

function managementEmpty(view) {
  return 'Chưa có yêu cầu ' + managementListLabel(view).toLowerCase() + '.';
}

function isManagementRoute(hash) {
  return hash === '#management' || hash.startsWith('#management/');
}

function showManagement() {
  show('management');
  const manager = user.role === 'MANAGER';
  const listRoute = managementListRoute(location.hash);
  const approved = listRoute === approvedRoute;
  const handedOver = listRoute === handedOverRoute;
  const detail = location.hash !== listRoute;
  const id = Number(/^\/(\d+)$/.exec(location.hash.slice(listRoute.length))?.[1]);
  const back = byId('management-back');
  back.href = listRoute;
  back.textContent = handedOver ? 'Về danh sách đã giao' : approved ? 'Về danh sách đã duyệt' : 'Về hàng đợi';
  byId('management-zone').hidden = !manager;
  byId('management-back').hidden = !manager || !detail;
  byId('management-list-title').hidden = !manager || detail;
  byId('management-refresh').hidden = true;
  byId('management-title').textContent = detail ? 'Chi tiết yêu cầu'
    : handedOver ? 'Yêu cầu đã giao' : approved ? 'Yêu cầu đã duyệt' : 'Duyệt yêu cầu mượn';
  byId('management-recovery').replaceChildren();
  byId('return-detail-link').hidden = true;
  const lookup = byId('return-lookup');
  lookup.hidden = !manager || !handedOver || detail;
  lookup.reset();
  message('return-lookup-error', '');
  message('management-feedback', '');
  if (!manager) return message('management-status', 'Bạn không có quyền truy cập.', true);
  if (detail && !(id > 0 && id <= 2147483647)) {
    return message('management-status', 'Đường dẫn yêu cầu không hợp lệ.', true);
  }
  managementView = { id: detail ? id : null, approved, handedOver, listRoute, items: [] };
  byId('management-refresh').hidden = false;
  void loadManagement(managementView);
}

function managementReadError(error) {
  if (error.status === 403) return 'Bạn không có quyền truy cập.';
  if (error.status === 404) return 'Không tìm thấy yêu cầu. Hãy quay lại và kiểm tra mã yêu cầu.';
  if (error.status === 400) return 'Đường dẫn yêu cầu không hợp lệ.';
  return 'Chưa tải được dữ liệu. Hãy thử lại.';
}

async function loadManagement(view, clear = true) {
  view.read?.abort();
  const read = new AbortController();
  view.read = read;
  const refresh = byId('management-refresh');
  refresh.disabled = true;
  refresh.textContent = 'Làm mới';
  if (clear) view.items = [];
  renderManagement(view);
  message('management-status', view.id ? 'Đang tải chi tiết…' : 'Đang tải danh sách…');
  try {
    const result = await api(view.id ? '/loan-requests/' + view.id : managementListPath(view), {
      signal: AbortSignal.any([read.signal, AbortSignal.timeout(15000)]),
    });
    if (read.signal.aborted) return;
    view.items = view.id ? [result] : result;
    renderManagement(view);
    message('management-status', view.items.length ? '' : managementEmpty(view));
  } catch (error) {
    if (read.signal.aborted) return;
    if (error.status === 401) return expired();
    view.items = [];
    renderManagement(view);
    message('management-status', managementReadError(error), true);
    refresh.textContent = 'Thử tải lại';
  } finally {
    if (!read.signal.aborted) refresh.disabled = false;
  }
}

function decisionButton(label, key, action) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.dataset.focusKey = key;
  button.addEventListener('click', action);
  return button;
}

function managementSummary(item) {
  return formatClubTime(item.start_at) + ' → ' + formatClubTime(item.end_at);
}

function returnReceipt(item) {
  if (item.status !== 'RETURNED' || !item.returned_at || !item.returned_by) return '';
  return 'Người nhận: ' + (item.returned_by_username || 'ID ' + item.returned_by)
    + ' · Giờ nhận: ' + formatClubTime(item.returned_at);
}

function renderManagement(view) {
  if (!view || view !== managementView) return;
  const currentDecision = managementDecisions.get(view.id);
  byId('management-refresh').hidden = Boolean(currentDecision?.physicalTransition
    && (currentDecision.sending || currentDecision.running || currentDecision.retry || currentDecision.unavailable));
  const rows = byId('management-rows');
  const recovery = byId('management-recovery');
  const focused = document.activeElement;
  const focusKey = rows.contains(focused) || recovery.contains(focused) ? focused.dataset.focusKey : null;
  const items = view.items;
  byId('management-list-title').textContent = managementListLabel(view) + ' (' + items.length + ')';
  if (view.id && items.length) byId('management-title').textContent = 'Yêu cầu #' + view.id;
  rows.replaceChildren(...items.map((item) => {
    const row = document.createElement('li');
    row.className = 'asset management-card';
    const info = document.createElement('div');
    const title = document.createElement('h3');
    title.textContent = item.equipment_name + ' · ' + item.equipment_asset_code;
    info.append(title);
    for (const text of [
      managementSummary(item),
      'YC-' + item.id + ' · Người gửi ' + item.borrower_username,
      'Gửi lúc ' + formatClubTime(item.created_at),
    ]) {
      const line = document.createElement('p');
      line.textContent = text;
      info.append(line);
    }
    const badge = document.createElement('span');
    badge.className = 'request-badge';
    badge.textContent = loanLabels[item.status] || item.status;
    info.append(badge);
    const receipt = returnReceipt(item);
    if (receipt) {
      const line = document.createElement('p');
      line.textContent = receipt;
      info.append(line);
    }
    const actions = document.createElement('div');
    actions.className = 'management-actions';
    const decision = managementDecisions.get(item.id);
    if (!view.id) {
      const link = document.createElement('a');
      link.href = view.listRoute + '/' + item.id;
      link.dataset.focusKey = item.id + '-detail';
      link.textContent = 'Chi tiết';
      actions.append(link);
    }
    if (view.approved && view.id && item.status === 'APPROVED') {
      const button = decisionButton('Xác nhận giao', item.id + '-handover', () =>
        void submitDecision({ item, verb: 'handover', user }));
      button.className = 'primary';
      button.disabled = Boolean(decision?.locked || managementBusy());
      actions.append(button);
    }
    if (view.handedOver && item.status === 'HANDED_OVER') {
      const label = 'Xác nhận nhận lại';
      const button = decisionButton(label, item.id + '-return', () => confirmDecision(item, 'return', label));
      button.className = 'primary';
      button.disabled = Boolean(decision?.locked || managementBusy());
      actions.append(button);
    }
    if (!view.approved && !view.handedOver && item.status === 'PENDING') {
      for (const [verb, label, style] of [['approve', 'Duyệt', 'primary'], ['reject', 'Từ chối', 'reject']]) {
        const button = decisionButton(label, item.id + '-' + verb, () => confirmDecision(item, verb, label));
        button.className = style;
        button.disabled = Boolean(decision?.locked || managementBusy());
        actions.append(button);
      }
    }
    row.append(info, actions);
    if (decision?.notice) {
      const notice = document.createElement('p');
      notice.className = 'management-warning';
      notice.textContent = decision.notice;
      row.append(notice);
    }
    return row;
  }));
  recovery.replaceChildren();
  for (const [id, decision] of managementDecisions) {
    if (!decision.retry || (view.id && view.id !== id)
      || (decision.handover && (!view.id || !view.approved))
      || (decision.returning && !view.handedOver)) continue;
    const retry = decisionButton(decision.retryLabel + ' YC-' + id, id + '-retry', decision.retry);
    retry.disabled = managementBusy();
    recovery.append(retry);
  }
  if (focusKey) {
    const next = [...byId('management').querySelectorAll('[data-focus-key]')]
      .find((node) => node.dataset.focusKey === focusKey && !node.disabled);
    (next || byId('management-title')).focus();
  }
}

function confirmDecision(item, verb, label) {
  if (loggingOut || managementBusy() || managementDecisions.get(item.id)?.locked) return;
  decisionSelection = { item, verb, user, view: managementView };
  decisionDialog.returnValue = '';
  byId('decision-title').textContent = verb === 'return' ? 'Nhận lại thiết bị · YC-' + item.id + '?'
    : label + ' yêu cầu YC-' + item.id + '?';
  byId('decision-confirm').textContent = verb === 'return' ? label : 'Xác nhận ' + label.toLowerCase();
  byId('decision-summary').textContent = item.equipment_name + ' · ' + item.equipment_asset_code
    + ' · ' + managementSummary(item);
  decisionDialog.showModal();
}

decisionDialog.addEventListener('close', () => {
  const selection = decisionSelection;
  decisionSelection = undefined;
  if (decisionDialog.returnValue === 'confirm' && selection && selection.view === managementView
    && selection.user === user && !loggingOut) void submitDecision(selection);
});

byId('management-refresh').addEventListener('click', () => {
  byId('management-title').focus();
  void loadManagement(managementView);
});

const returnLookupInput = byId('return-lookup-id');
byId('return-lookup').addEventListener('submit', (event) => {
  event.preventDefault();
  if (user?.role !== 'MANAGER' || location.hash !== handedOverRoute || loggingOut) return;
  const id = Number(/^(?:YC-)?(\d+)$/i.exec(returnLookupInput.value.trim())?.[1]);
  if (!(id > 0 && id <= 2147483647)) {
    message('return-lookup-error', 'Nhập mã yêu cầu hợp lệ, ví dụ YC-42.', true);
    returnLookupInput.focus();
    return;
  }
  message('return-lookup-error', '');
  location.hash = handedOverRoute + '/' + id;
});

async function submitDecision({ item, verb, user: session }) {
  const id = item.id;
  if (session !== user || session?.role !== 'MANAGER' || loggingOut
    || managementBusy() || managementDecisions.get(id)?.locked) return;
  const path = '/loan-requests/' + id;
  const handover = verb === 'handover';
  const returning = verb === 'return';
  const physicalTransition = handover || returning;
  const decision = { locked: true, sending: true, handover, returning, physicalTransition };
  managementDecisions.set(id, decision);
  const feedback = (text, error = false) => {
    if (managementView) message('management-feedback', 'YC-' + id + ' · ' + text, error);
  };
  if (returning) {
    byId('return-detail-link').hidden = true;
    feedback('Đang xác nhận nhận lại…');
  } else if (handover) feedback('Đang xác nhận giao…');
  else decision.notice = 'Đang gửi quyết định…';
  const refreshView = () => {
    if (managementView) void loadManagement(managementView, false);
  };
  const applyPhysicalStatus = (fresh) => {
    managementDecisions.delete(id);
    const view = managementView;
    const receipt = returning && returnReceipt(fresh);
    let result = 'Trạng thái đã đọc: ' + (loanLabels[fresh.status] || fresh.status) + '.';
    if (receipt) result = 'Đã trả. ' + receipt + '.';
    if (handover && decision.sending) result = 'Đã xác nhận giao thiết bị.';
    feedback(result);
    if (view?.id === id) {
      view.read?.abort();
      view.items = [fresh];
      byId('management-refresh').disabled = false;
      byId('management-refresh').textContent = 'Làm mới';
      message('management-status', '');
    } else if (view && !view.id && (returning ? view.handedOver : view.approved)) {
      if (returning && fresh.status === 'RETURNED') {
        const link = byId('return-detail-link');
        link.href = handedOverRoute + '/' + id;
        link.textContent = 'Xem chi tiết YC-' + id;
        link.hidden = false;
      }
      view.items = view.items.flatMap((entry) => {
        if (entry.id !== id) return [entry];
        return fresh.status === (returning ? 'HANDED_OVER' : 'APPROVED') ? [fresh] : [];
      });
      refreshView();
    }
    renderManagement(view);
  };
  const reconcile = async (refreshSession = false) => {
    if (user !== session || managementBusy()) return;
    decision.running = true;
    decision.retry = undefined;
    if (physicalTransition) feedback(returning ? decision.notice + ' Đang tải lại chi tiết…' : 'Đang tải lại trạng thái…');
    renderManagement(managementView);
    try {
      if (refreshSession) {
        const current = await api('/auth/me', { signal: AbortSignal.timeout(15000) });
        if (sessionVerification) await sessionVerification.promise;
        if (user !== session) return;
        if (current.id !== session.id || current.role !== session.role) return expired();
        session.csrf_token = current.csrf_token;
      }
      let fresh = await api(path, { signal: AbortSignal.timeout(15000) });
      if (sessionVerification) await sessionVerification.promise;
      if (user !== session) return;
      if (physicalTransition) return applyPhysicalStatus(fresh);
      const queue = await api('/loan-requests', { signal: AbortSignal.timeout(15000) });
      if (sessionVerification) await sessionVerification.promise;
      if (user !== session) return;
      const pendingInQueue = queue.some((entry) => entry.id === id);
      if (fresh.status === 'PENDING' && !pendingInQueue) {
        fresh = await api(path, { signal: AbortSignal.timeout(15000) });
        if (sessionVerification) await sessionVerification.promise;
        if (user !== session) return;
      }
      decision.locked = false;
      if (fresh.status !== 'PENDING' || !pendingInQueue) {
        managementDecisions.delete(id);
      }
      feedback(decision.notice + ' Trạng thái đã đọc: ' + (loanLabels[fresh.status] || fresh.status) + '.');
      const view = managementView;
      if (view && ((!view.approved && !view.handedOver && !view.id) || view.id === id)) {
        view.read?.abort();
        byId('management-refresh').disabled = false;
        byId('management-refresh').textContent = 'Làm mới';
        view.items = view.id ? [fresh] : queue.filter((entry) => entry.id !== id || fresh.status === 'PENDING');
        message('management-status', view.items.length ? '' : 'Chưa có yêu cầu đang chờ.');
      }
    } catch (error) {
      if (sessionVerification) await sessionVerification.promise;
      if (user !== session) return;
      if (error.status === 401) return expired();
      decision.retryLabel = refreshSession ? 'Làm mới phiên và tải lại'
        : returning ? 'Thử tải lại chi tiết' : 'Tải lại trạng thái';
      decision.retry = () => void reconcile(refreshSession);
      feedback(decision.notice + ' ' + managementReadError(error), true);
    } finally {
      decision.running = false;
      if (user === session) renderManagement(managementView);
    }
  };
  renderManagement(managementView);
  try {
    const saved = await api(path + '/' + verb, {
      method: 'POST',
      headers: { 'X-CSRF-Token': session.csrf_token },
      signal: AbortSignal.timeout(15000),
    });
    if (sessionVerification) await sessionVerification.promise;
    if (user !== session) return;
    if (physicalTransition) return applyPhysicalStatus({ ...item, ...saved });
    managementDecisions.delete(id);
    feedback((loanLabels[saved.status] || saved.status) + '.');
    if (managementView) {
      const view = managementView;
      view.items = view.id
        ? view.items.map((entry) => entry.id === id ? { ...entry, status: saved.status } : entry)
        : view.items.filter((entry) => entry.id !== id);
    }
    refreshView();
  } catch (error) {
    if (sessionVerification) await sessionVerification.promise;
    if (user !== session) return;
    decision.sending = false;
    if (error.status === 401) return expired();
    if (physicalTransition) {
      const refreshSession = error.message === 'CSRF_INVALID';
      if (error.message === 'EQUIPMENT_IN_USE') {
        managementDecisions.delete(id);
        feedback('Thiết bị vẫn đang được giữ. Hãy xác nhận nhận lại trước khi giao lượt này.', true);
      } else if (!refreshSession && [400, 403, 404].includes(error.status)) {
        if (managementView?.id === id) {
          decision.blockedView = managementView;
          if (error.status !== 403) {
            decision.unavailable = true;
            managementView.read?.abort();
            managementView.items = [];
            byId('management-refresh').hidden = true;
            message('management-status', '');
          }
        } else {
          managementDecisions.delete(id);
          if (returning) refreshView();
        }
        feedback(managementReadError(error), true);
      } else {
        decision.notice = refreshSession ? 'Không xác thực được thao tác. Hãy làm mới phiên.'
          : error.message === 'INVALID_TRANSITION' ? 'Yêu cầu đã đổi trạng thái. Hãy tải lại chi tiết.'
            : returning ? 'Chưa xác định được kết quả.'
              : 'Chưa xác định được kết quả. Hãy tải lại chi tiết trước khi giao lại.';
        if (returning) return reconcile(refreshSession);
        decision.retryLabel = refreshSession ? 'Làm mới phiên và tải lại' : 'Tải lại chi tiết';
        decision.retry = () => void reconcile(refreshSession);
        feedback(decision.notice, true);
      }
      return renderManagement(managementView);
    }
    switch (error.message) {
      case 'SCHEDULE_CONFLICT':
        decision.notice = 'Thiết bị đã có lịch trùng với khung giờ này.';
        break;
      case 'INVALID_TRANSITION':
        decision.notice = 'Yêu cầu đã đổi trạng thái.';
        break;
      case 'CSRF_INVALID':
        decision.notice = 'Phiên thao tác cần làm mới.';
        break;
      case 'FORBIDDEN':
        decision.notice = 'Bạn không có quyền thực hiện thao tác này.';
        break;
      case 'ORIGIN_FORBIDDEN':
      case 'INVALID_INPUT':
      case 'NOT_FOUND':
        managementDecisions.delete(id);
        feedback(error.message === 'ORIGIN_FORBIDDEN' ? 'Địa chỉ ứng dụng không được phép thao tác.'
          : managementReadError(error), true);
        return refreshView();
      default:
        decision.notice = 'Chưa xác định được kết quả. Đang đối chiếu trạng thái yêu cầu.';
    }
    feedback(decision.notice, true);
    await reconcile(['CSRF_INVALID', 'FORBIDDEN'].includes(error.message));
  }
}

function managementBusy() {
  return [...managementDecisions.values()].some((entry) => entry.sending || entry.running);
}

function isLoanRoute(hash) {
  return hash === '#requests' || hash.startsWith('#request/');
}

function showBusinessScreen() {
  if (isLoanRoute(location.hash)) {
    showLoanScreen();
    return;
  }
  const availabilityRoute = /^#availability\/(\d+)$/.exec(location.hash);
  if (availabilityRoute) {
    show('availability');
    message('lookup-status', 'Chọn khoảng thời gian rồi xem lịch trống.');
    void loadCatalog(availabilityRoute[1]);
    return;
  }
  if (isManagementRoute(location.hash)) {
    showManagement();
    return;
  }
  history.replaceState(null, '', '#equipment');
  show('equipment');
  void loadCatalog();
}

async function checkSession() {
  if (checkingSession || loggingOut) return;
  checkingSession = true;
  // Keep decision responses waiting across a failed check and its retry.
  sessionVerification ??= { ...Promise.withResolvers(), previous: user };
  const { previous, resolve } = sessionVerification;
  let verified = false;
  user = null;
  show('session');
  byId('session-retry').hidden = true;
  message('session-status', 'Đang kiểm tra phiên…');
  try {
    const current = await api('/auth/me', { signal: AbortSignal.timeout(15000) });
    verified = true;
    if (previous && current.id === previous.id && current.role === previous.role
      && current.csrf_token === previous.csrf_token) {
      user = previous;
    } else {
      managementDecisions.clear();
      user = current;
    }
    showBusinessScreen();
  } catch (error) {
    if (error.status === 401) {
      verified = true;
      if (previous) expired();
      else if (location.hash === '#register') showRegistration();
      else {
        if (isLoanRoute(location.hash) || isManagementRoute(location.hash)) loanLoginRoute = location.hash;
        endSession((loanLoginRoute || ['#equipment', '#management'].includes(location.hash) || location.hash.startsWith('#availability/'))
          ? 'Vui lòng đăng nhập để tiếp tục.' : '');
      }
    } else {
      message('session-status', 'Không kiểm tra được phiên đăng nhập.', true);
      byId('session-retry').hidden = false;
    }
  } finally {
    checkingSession = false;
    if (verified) {
      sessionVerification = undefined;
      resolve();
    }
  }
}

function loginError(error) {
  switch (error.message) {
    case 'INVALID_CREDENTIALS':
      return 'Tên đăng nhập hoặc mật khẩu không đúng.';
    case 'INVALID_INPUT':
      return 'Vui lòng kiểm tra tên đăng nhập và mật khẩu.';
    case 'LOGIN_RATE_LIMITED':
      return error.retryAfter > 0
        ? 'Quá nhiều lần thử. Vui lòng thử lại sau ' + error.retryAfter + ' giây.'
        : 'Quá nhiều lần thử. Vui lòng thử lại sau.';
    case 'ORIGIN_FORBIDDEN':
      return 'Địa chỉ ứng dụng không được phép đăng nhập.';
    default:
      return 'Chưa thể đăng nhập. Vui lòng thử lại.';
  }
}

byId('login-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = byId('submit');
  if (submit.disabled) return;
  const username = byId('username').value.trim();
  if (!username) {
    message('login-status', 'Vui lòng nhập tên đăng nhập.', true);
    byId('username').focus();
    return;
  }
  submit.disabled = true;
  message('login-status', 'Đang đăng nhập…');
  const password = byId('password').value;
  byId('password').value = '';
  try {
    user = await api('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    history.replaceState(null, '', loanLoginRoute || '#equipment');
    loanLoginRoute = undefined;
    showBusinessScreen();
  } catch (error) {
    byId('password').value = '';
    message('login-status', loginError(error), true);
    byId('password').focus();
  } finally {
    submit.disabled = false;
  }
});

async function logout() {
  if (!user || loggingOut) return;
  const session = user;
  loggingOut = true;
  byId('logout').disabled = true;
  message('action-status', 'Đang đăng xuất…');
  try {
    await api('/auth/logout', {
      method: 'POST',
      headers: { 'X-CSRF-Token': session.csrf_token },
    });
    if (user === session) endSession();
  } catch (error) {
    if (user !== session) return;
    if (error.status === 401) return expired();
    if (error.message === 'CSRF_INVALID') {
      try {
        const refreshed = await api('/auth/me');
        if (user !== session) return;
        managementDecisions.clear();
        user = refreshed;
      } catch (refreshError) {
        if (refreshError.status === 401) return expired();
      }
      if (user) showBusinessScreen();
    }
    if (user) message('action-status', error.message === 'FORBIDDEN'
      ? 'Bạn không có quyền thực hiện thao tác này.'
      : 'Chưa xác nhận được đăng xuất. Vui lòng thử lại.', true);
  } finally {
    loggingOut = false;
    byId('logout').disabled = false;
  }
}

for (const button of document.querySelectorAll('[data-demo]')) {
  button.addEventListener('click', () => {
    byId('username').value = button.dataset.demo;
    byId('password').value = '';
    byId('password').focus();
  });
}
byId('retry').addEventListener('click', () => {
  byId('equipment-title').focus();
  void loadCatalog();
});
byId('session-retry').addEventListener('click', checkSession);
byId('lookup-catalog-retry').addEventListener('click', () => {
  byId('availability-title').focus();
  void loadCatalog(location.hash.slice('#availability/'.length));
});
byId('lookup').addEventListener('submit', lookupAvailability);
byId('lookup-retry').addEventListener('click', () => {
  byId('lookup').querySelector('button').focus();
  byId('lookup').requestSubmit();
});
byId('lookup').addEventListener('input', () => {
  clearAvailability('Lựa chọn đã thay đổi. Xem lịch trống để cập nhật.');
});
byId('logout').addEventListener('click', logout);
byId('register-form').addEventListener('submit', submitRegistration);
byId('register-form').addEventListener('input', (event) => {
  fieldError(event.target);
  message('register-error', '');
});
byId('request-form').addEventListener('submit', submitLoan);
byId('request-form').addEventListener('input', (event) => fieldError(event.target));
byId('request-catalog-retry').addEventListener('click', () => {
  const params = new URLSearchParams(location.hash.split('?')[1]);
  void loadLoanCatalog(loanView, loanDevice.value || (!loanDevice.options.length && params.get('equipment_id')) || '');
});
window.addEventListener('hashchange', () => {
  if (checkingSession || byId('session').hidden === false) return;
  if (user) showBusinessScreen();
  else if (byId('submit').disabled) history.replaceState(null, '', '#login');
  else if (location.hash === '#register') showRegistration();
  else if (location.hash === '#login') endSession();
  else if (location.hash !== '#register/success' || byId('register-success').hidden) {
    if (isLoanRoute(location.hash) || isManagementRoute(location.hash)) loanLoginRoute = location.hash;
    endSession('Vui lòng đăng nhập để tiếp tục.');
  }
});
window.addEventListener('pageshow', (event) => {
  if (event.persisted) void checkSession();
});
void checkSession();
