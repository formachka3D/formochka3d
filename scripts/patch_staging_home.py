"""Apply a minimal service-directory and login-header enhancement to STAGING ONLY.

Run: python3 scripts/patch_staging_home.py /opt/formochka3d-staging/web/app.py
Reversible: app.py.before_home_20260926 is saved beside app.py first.
"""
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
if 'class="service-directory"' in source:
    print("Already installed; no changes")
    sys.exit(0)
assert 'PAGE = """' in source
assert 'class="page-shell"' in source
assert source.count("</style>") == 1
assert source.count('    <div class="modes" id="generator">') == 1
assert source.count('            <a href="/account/">Личный кабинет</a>') == 1
assert source.count("</body>") == 1

backup = path.with_name("app.py.before_home_20260926")
if not backup.exists():
    backup.write_text(source, encoding="utf-8")

styles = """
        /* Staging landing page: quiet service directory above existing generators. */
        .page-shell {padding-top: clamp(145px, 19vw, 225px);}
        .service-directory {max-width:1060px;margin:0 auto 48px;text-align:center;}
        .service-directory h1 {font:800 clamp(29px,4vw,42px)/1.15 Arial,sans-serif;
            margin:0 0 10px;color:#6f4544;}
        .service-directory p {color:#816c65;margin:0 0 28px;font-size:17px;}
        .service-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;}
        .service-tile {background:#fffdfb;border:1px solid #f2dcd1;border-radius:24px;
            box-shadow:0 14px 38px #79504415;display:block;text-align:left;
            padding:28px;text-decoration:none;min-height:215px;color:#523d39;}
        a.service-tile {transition:transform .15s,box-shadow .15s;}
        a.service-tile:hover {transform:translateY(-4px);box-shadow:0 18px 44px #79504423;}
        .service-tile .picture {display:block;font-size:53px;margin-bottom:16px;}
        .service-tile h2 {font-size:22px;margin:0 0 11px;color:#523d39;}
        .service-tile p {font-size:14px;margin:0;color:#806b62;line-height:1.55;}
        .service-tile .soon {font-size:12px;color:#b87969;font-weight:700;margin-top:15px}
        .service-tile.future {background:#fff9f5;opacity:.85;}
        .header-user {display:flex;align-items:center;gap:7px;background:#fff0e8;
          border:1px solid #f3dacf;border-radius:22px;padding:6px 12px!important;}
        #account-entry {white-space:nowrap;}
        .ginger-backdrop {position:fixed;inset:0;z-index:10000;background:#3224289c;display:none;
          align-items:center;justify-content:center;padding:16px;}
        .ginger-backdrop[aria-hidden="false"] {display:flex;}
        .ginger-modal {position:relative;max-width:430px;width:100%;background:#fff9f7;border:2px solid #f2bfd2;
          border-radius:30px;padding:33px 25px;text-align:center;box-shadow:0 26px 60px #3d202940;}
        .ginger-modal h2 {color:#964c69;font-size:29px;margin:6px 0 12px;}
        .ginger-modal p {color:#76515d;line-height:1.5;}
        .ginger-modal .ginger-cta {display:inline-block;margin-top:13px;padding:13px 22px;
          background:#ce6389;color:white;text-decoration:none;border-radius:15px;font-weight:700;}
        .ginger-modal .ginger-close {position:absolute;top:13px;right:16px;border:0;background:transparent;
          color:#87576b;font-size:27px;cursor:pointer;}
        @media (max-width:760px) {
            .service-grid {grid-template-columns:1fr;gap:12px}
            .service-tile {min-height:130px;padding:19px}
            .service-tile .picture {font-size:35px;float:left;margin:0 16px 25px 0}
            .service-directory {margin-bottom:33px}
            .page-shell {padding-top:105px}
        }
"""
source = source.replace("</style>", styles + "\n    </style>", 1)
source = source.replace(
    '            <a href="/account/">Личный кабинет</a>',
    '            <a id="account-entry" href="/account/">Войти</a>', 1)
# Keep the top bar intentionally minimal: logo on the left, login on the right.
nav_start = source.index('<nav class="topnav">')
nav_end = source.index('</nav>', nav_start) + len('</nav>')
source = source[:nav_start] + ('''<nav class="topnav">
            <a id="account-entry" href="/account/">Войти</a>
        </nav>''') + source[nav_end:]

landing = """
    <section class="service-directory" aria-label="Наши сервисы">
        <h1>Что создадим сегодня? 🍓</h1>
        <p>Выбирай нужный раздел. Регистрация для просмотра не требуется.</p>
        <div class="service-grid">
            <a class="service-tile" href="#generator">
                <span class="picture" aria-hidden="true">🍪</span>
                <h2>Создать STL</h2>
                <p>Преврати картинку или надпись в формочку для 3D-печати.</p>
            </a>
            <div class="service-tile future">
                <span class="picture" aria-hidden="true">🧁</span>
                <h2>Готовые формочки</h2>
                <p>Библиотека готовых моделей для печати.</p>
                <div class="soon">СКОРО</div>
            </div>
            <div class="service-tile future">
                <span class="picture" aria-hidden="true">💌</span>
                <h2>Ответы на отзывы</h2>
                <p>Удобная работа с отзывами магазина в одном месте.</p>
                <div class="soon">СКОРО</div>
            </div>
        </div>
    </section>

"""
source = source.replace('    <div class="modes" id="generator">', landing +
                        '    <div class="modes" id="generator">', 1)
welcome = """
<div id="ginger-backdrop" class="ginger-backdrop" aria-hidden="true">
  <section class="ginger-modal" role="dialog" aria-modal="true" aria-labelledby="ginger-title">
    <button type="button" id="ginger-close" class="ginger-close" aria-label="Закрыть">×</button>
    <div aria-hidden="true" style="font-size:60px">🍓🍪💗</div>
    <h2 id="ginger-title">Получи 10 пряничков!</h2>
    <p>Зарегистрируйся, подтверди почту и получи приветственные баллы.
       В будущем их можно будет обменивать на скидки и приятные подарки!</p>
    <a class="ginger-cta" href="/account/?mode=register">Забрать прянички</a>
    <p style="font-size:13px">Программа наград скоро появится.</p>
  </section>
</div>
"""
source = source.replace("</body>", welcome + "\n</body>", 1)
header_js = """
<script>
/* Display a logged-in member's own name or chosen avatar without showing admin links. */
fetch('/account/api/me',{credentials:'same-origin',cache:'no-store'})
  .then(r=>r.ok?r.json():null)
  .then(me=>{
      if(!me||!me.authenticated){
          try {
            if(!sessionStorage.getItem('f3d-ginger-welcome-v1')) {
              const dialog=document.getElementById('ginger-backdrop');
              dialog.setAttribute('aria-hidden','false');
              sessionStorage.setItem('f3d-ginger-welcome-v1','1');
              document.getElementById('ginger-close').focus();
            }
          }catch(e){} // Browser privacy modes should not break the site.
          return;
      }
      const a=document.getElementById('account-entry');
      if(!a)return;
      a.classList.add('header-user');
      a.replaceChildren();
      if(me.has_photo) {
          const img=document.createElement('img');
          img.src=me.avatar_url;img.alt='';img.width=29;img.height=29;
          img.style.borderRadius='50%';img.style.objectFit='cover';
          a.append(img);
      } else {
          const face=document.createElement('span');face.textContent=me.avatar||'🍪';
          face.style.fontSize='24px';a.append(face);
      }
      const name=document.createElement('span');name.textContent=me.name||'Кабинет';
      a.append(name);
  }).catch(()=>{});
function closeGinger(){document.getElementById('ginger-backdrop').setAttribute('aria-hidden','true')}
document.getElementById('ginger-close').addEventListener('click',closeGinger);
document.getElementById('ginger-backdrop').addEventListener('click',e=>{
  if(e.target.id==='ginger-backdrop')closeGinger();
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&document.getElementById('ginger-backdrop').getAttribute('aria-hidden')==='false')closeGinger();
});
</script>
"""
source = source.replace("</body>", header_js + "\n</body>", 1)
path.write_text(source, encoding="utf-8")
print("Staging homepage directory and member header installed")
