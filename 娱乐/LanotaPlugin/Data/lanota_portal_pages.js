const data = window.__LANOTA_DATA__;
const byId = id => document.getElementById(id);
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function metric(value, label, alert = false) {
  const box = el('div', null, alert ? 'metric alert' : 'metric');
  box.append(el('b', value), el('small', label));
  return box;
}
function song(row) {
  const title = el('span', row.name, 'title');
  title.append(el('span', '#' + row.id, 'song-id'));
  return title;
}
function difficulty(row) {
  const text = row.difficulty || '—';
  const diff = el('span', text + (row.level == null ? '' : ' ' + row.level), 'badge');
  const key = String(text).toLowerCase();
  if (['whisper', 'acoustic', 'ultra', 'master'].includes(key)) diff.style.color = `var(--${key})`;
  return diff;
}
function chapter(value) {
  const label = el('span', value || '—', 'chapter');
  const chapterKey = String(value || '').split('-')[0];
  let hash = 0;
  for (const c of chapterKey) hash = (hash * 31 + c.codePointAt(0)) >>> 0;
  const palette = ['whisper','master','gold','acoustic','ultra'];
  label.style.setProperty('--chapter', `var(--${palette[hash % palette.length]})`);
  return label;
}
function cell(value, className) {
  const td = el('td', null, className);
  td.append(value);
  return td;
}
function fitPage() {
  const page = document.querySelector('main');
  const fit = () => {
    // 自定义字体和超长标题可能改变行数；按最终排版缩放，不截断最后一行。
    page.style.zoom = '1';
    const height = page.getBoundingClientRect().height;
    if (height > innerHeight) page.style.zoom = String((innerHeight - 2) / height);
  };
  fit();
  document.fonts.ready.then(fit);
}
