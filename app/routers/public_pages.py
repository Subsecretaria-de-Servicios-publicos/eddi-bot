from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter(tags=["public-pages"])


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
    request,
    "chat.html",
    {"request": request},
)


@router.get("/rag/eddi/embed.js")
def embed_js():
    js = """
(function(){
  if (window.EDDIChat) return;

  window.EDDIChat = {
    init: function(config){
      var btn = document.createElement('button');
      btn.id = 'eddi-chat-launcher';
      btn.innerHTML = '💬';
      document.body.appendChild(btn);

      var panel = document.createElement('div');
      panel.id = 'eddi-chat-panel';
      panel.innerHTML = `
        <div id="eddi-chat-header">EDDI</div>
        <iframe src="${config.apiBase || ''}/" style="width:100%;height:calc(100% - 48px);border:none;"></iframe>
      `;
      document.body.appendChild(panel);

      var style = document.createElement('style');
      style.innerHTML = `
        #eddi-chat-launcher{
          position:fixed; right:24px; bottom:24px; width:56px; height:56px;
          border:none; border-radius:999px; background:#041e37; color:#fff;
          z-index:99999; cursor:pointer; box-shadow:0 8px 20px rgba(0,0,0,.25);
        }
        #eddi-chat-panel{
          position:fixed; right:24px; bottom:90px; width:380px; height:640px;
          background:#fff; border-radius:18px; overflow:hidden; display:none;
          z-index:99999; box-shadow:0 20px 50px rgba(0,0,0,.25);
          border:1px solid rgba(0,0,0,.08);
        }
        #eddi-chat-header{
          height:48px; display:flex; align-items:center; padding:0 14px;
          background:#041e37; color:#fff; font-weight:700;
        }
      `;
      document.head.appendChild(style);

      btn.onclick = function(){
        panel.style.display = panel.style.display === 'none' || !panel.style.display ? 'block' : 'none';
      };
    }
  };
})();
    """
    return Response(content=js, media_type="application/javascript")