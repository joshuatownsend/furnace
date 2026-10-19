"""A read-only piano roll of a song (ideas/013, spike step 3): one HTML page,
time across in rows, written pitch up, each note a bar, a color per channel.

A bar runs from its note to the next note, note off (OFF) or note release (===)
in the same channel, or to the end of the range. Macro release (REL) does not
end it. Bars carry across orders. An order ends early on a jump or pattern
break (0Bxx, 0Dxx, FFxx) in any channel; the row 0Dxx skips to is ignored.
Pitch effects (arpeggio, slides, vibrato, detune) are markers, not drawn
pitch: the roll shows what is written, like the pattern view.

    python -m furnace_mcp.roll song.fur -o song.html [--orders 0-3] [--channels 0,2]
"""

import argparse
import json
from pathlib import Path

from . import notation
from . import song as fsong

ORDER_ENDS = {0x0B, 0x0D, 0xFF}  # jump to order, next order, stop song
# effects that change the heard pitch of a note
PITCH_FX = {0x00: "arpeggio", 0x01: "slide up", 0x02: "slide down", 0x03: "portamento",
            0x04: "vibrato", 0xE1: "note slide up", 0xE2: "note slide down", 0xE5: "detune"}

# one per channel, cycled; a channel's custom color wins
PALETTE = ["#5fb8ff", "#ff7a6b", "#7be08a", "#ffcc4d", "#c792ff", "#4de0d0",
           "#ff8fd0", "#b8d65a", "#ffa94d", "#8fa8ff", "#e0e0e0", "#d6a36b"]


def _effects(row):
    return [(e.get("code", -1), e.get("value", -1)) for e in row.get("effects", [])
            if e.get("code", -1) >= 0]


def _order_rows(sub, o, chans, plen):
    """Rows order o plays before a jump or break ends it (across all channels,
    shown or not: a break in a hidden channel still ends the order)."""
    for r in range(plen):
        for c in chans:
            pat = fsong._pattern(sub, c, sub["orders"][c][o])
            rows = (pat or {}).get("rows", [])
            if r < len(rows) and any(code in ORDER_ENDS for code, _ in _effects(rows[r] or {})):
                return r + 1
    return plen


def _ins_name(song, ins):
    insts = song.get("instruments") or []
    return insts[ins].get("name", "") if 0 <= ins < len(insts) else ""


def notes(song, sub_index=0, order_start=0, order_end=None, channels=None):
    """The roll's data: orders (start row and length in the shown range),
    channels (label, color), notes (bars) and marks (pitch effects and REL).
    Positions are rows from the start of order_start."""
    sub = fsong.subsong(song, sub_index)
    nchans = len(sub.get("orders") or [])
    olen = sub.get("orderLength", 0)
    if order_end is None:
        order_end = olen - 1
    order_end = min(order_end, olen - 1)
    if not 0 <= order_start <= order_end:
        raise IndexError(f"order range {order_start}-{order_end} invalid (song has {olen} orders)")
    chans = fsong._parse_channels(channels, nchans)
    plen = sub.get("patternLength", 64)
    labels = fsong.channel_labels(song)
    cdata = sub.get("channelData") or []

    out_chans = []
    for k, c in enumerate(chans):
        cd = cdata[c] if c < len(cdata) else {}
        col = cd.get("color")
        out_chans.append({
            "ch": c,
            "label": cd.get("name") or (labels[c] if c < len(labels) else f"channel {c}"),
            "color": f"#{col['r']:02x}{col['g']:02x}{col['b']:02x}" if col else PALETTE[k % len(PALETTE)],
        })

    orders, bars, marks = [], [], []
    open_bar = [None] * len(chans)  # the bar each channel is holding
    last_ins = [-1] * len(chans)  # a note with no instrument plays the last one
    x = 0
    for o in range(order_start, order_end + 1):
        n = _order_rows(sub, o, range(nchans), plen)
        orders.append({"order": o, "start": x, "rows": n,
                       "pats": [sub["orders"][c][o] for c in chans]})
        for k, c in enumerate(chans):
            pat = fsong._pattern(sub, c, sub["orders"][c][o])
            rows = (pat or {}).get("rows", [])
            cols = fsong._effect_cols(sub, c)
            for r in range(n):
                row = (rows[r] if r < len(rows) else None) or {}
                note = row.get("note", -1)
                here = x + r
                if note >= 0 and note != notation.MACRO_RELEASE and open_bar[k] is not None:
                    open_bar[k]["len"] = here - open_bar[k]["x"]
                    open_bar[k] = None
                if row.get("ins", -1) >= 0:
                    last_ins[k] = row["ins"]
                cell = notation.format_row(row, cols)
                where = f"{o:02X}:{r:02X}"
                if 0 <= note <= 179:
                    ins = last_ins[k]
                    bar = {"c": k, "x": here, "len": 0, "n": note, "name": notation.note_name(note),
                           "ins": ins, "insName": _ins_name(song, ins), "at": where, "cell": cell}
                    bars.append(bar)
                    open_bar[k] = bar
                held = open_bar[k]
                fx = [PITCH_FX[code] + f" {val:02X}" for code, val in _effects(row)
                      if code in PITCH_FX and (code, val) != (0xE5, 0x80)]  # E580 = no detune
                if note == notation.MACRO_RELEASE:
                    fx.append("macro release")
                if fx:
                    marks.append({"c": k, "x": here, "n": held["n"] if held else None,
                                  "what": ", ".join(fx), "at": where, "cell": cell})
        x += n
    for b in open_bar:
        if b is not None:
            b["len"] = x - b["x"]
    return {
        "title": song.get("songInfo", {}).get("name") or sub.get("name") or "",
        "subsong": sub_index,
        "rows": x,
        "highlights": (sub.get("highlights") or [4, 16])[:2],
        "orders": orders,
        "channels": out_chans,
        "notes": bars,
        "marks": marks,
    }


def html(data):
    """A self-contained page (no network) that draws the roll from notes()."""
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    return _PAGE.replace("/*DATA*/null", blob).replace("<!--TITLE-->", _esc(data["title"] or "Piano roll"))


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write(song, out, **kw):
    data = notes(song, **kw)
    Path(out).write_text(html(data), encoding="utf-8")
    return data


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><!--TITLE--> - piano roll</title>
<style>
:root{--bg:#16181d;--lane:#1c1f26;--black:#14161a;--grid:#262a33;--beat:#2e333d;--bar:#434957;
--order:#7a8090;--text:#d8dce4;--dim:#8a909c;--panel:#1e2128}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--text);font:13px/1.4 system-ui,sans-serif}
body{display:flex;flex-direction:column}
header{padding:8px 12px;display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;background:var(--panel);border-bottom:1px solid var(--grid)}
h1{font-size:15px;margin:0;font-weight:600}
.legend{display:flex;flex-wrap:wrap;gap:4px}
.chan{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border:1px solid var(--grid);border-radius:4px;background:none;color:var(--text);font:inherit;cursor:pointer}
.chan i{width:10px;height:10px;border-radius:2px;display:inline-block}
.chan.off{opacity:.35}
.chan small{color:var(--dim)}
label{color:var(--dim);display:inline-flex;gap:6px;align-items:center}
.hint{color:var(--dim);font-size:12px}
#wrap{flex:1;overflow:auto;position:relative}
#grid{display:grid;grid-template-columns:44px auto;grid-template-rows:22px auto;width:max-content}
#corner{position:sticky;left:0;top:0;z-index:3;background:var(--panel)}
#ruler{position:sticky;top:0;z-index:2;background:var(--panel)}
#keys{position:sticky;left:0;z-index:2;background:var(--panel)}
svg{display:block}
.note{stroke:rgba(0,0,0,.45);stroke-width:1}
.note:hover,.note.same{stroke:#fff;stroke-width:1.5}
.nlabel{fill:#111;font:10px ui-monospace,monospace;pointer-events:none}
.mark{fill:#fff;stroke:#000;stroke-width:.75;pointer-events:all}
.keytext{fill:var(--dim);font:10px ui-monospace,monospace}
#keys .keytext{fill:#333}
.otext{fill:var(--text);font:11px ui-monospace,monospace}
#tip{position:fixed;pointer-events:none;background:#0d0f12f0;border:1px solid var(--bar);border-radius:4px;padding:6px 8px;font:12px ui-monospace,monospace;white-space:pre;display:none;z-index:9}
</style></head><body>
<header>
<h1 id="title"></h1>
<div class="legend" id="legend"></div>
<label>Zoom <input type="range" id="zoom" min="3" max="40" value="12"></label>
<label>Height <input type="range" id="kh" min="5" max="20" value="10"></label>
<span class="hint">Click a channel to hide it, double-click to show it alone. Hover a note for its tracker cell.</span>
</header>
<div id="wrap"><div id="grid">
<div id="corner"></div><svg id="ruler"></svg>
<svg id="keys"></svg><svg id="roll"></svg>
</div></div>
<div id="tip"></div>
<script>
const D=/*DATA*/null;
const NS="http://www.w3.org/2000/svg";
const NAMES=["C-","C#","D-","D#","E-","F-","F#","G-","G#","A-","A#","B-"];
const BLACK=new Set([1,3,6,8,10]);
const hidden=new Set();
let rw=12,kh=10;
const ps=D.notes.map(n=>n.n);
const lo=Math.max(0,(ps.length?Math.min(...ps):108)-2), hi=Math.min(179,(ps.length?Math.max(...ps):119)+2);
const nname=n=>{const o=Math.floor(n/12)-5;return o<0?NAMES[n%12].toLowerCase().replace("-","_").replace("#","+")+(-o):NAMES[n%12]+o};
const hex=v=>v<0?"..":v.toString(16).toUpperCase().padStart(2,"0");
document.getElementById("title").textContent=(D.title||"Untitled")+(D.subsong?` (sub-song ${D.subsong})`:"");
function el(tag,attrs,parent){const e=document.createElementNS(NS,tag);for(const k in attrs)e.setAttribute(k,attrs[k]);if(parent)parent.appendChild(e);return e}
function legend(){
  const L=document.getElementById("legend");L.innerHTML="";
  D.channels.forEach((c,k)=>{
    const b=document.createElement("button");b.className="chan"+(hidden.has(k)?" off":"");
    const cnt=D.notes.filter(n=>n.c===k).length;
    b.innerHTML=`<i style="background:${c.color}"></i>${c.label.replace(/[&<]/g,s=>s==="&"?"&amp;":"&lt;")} <small>${cnt}</small>`;
    let t=null;
    b.onclick=()=>{clearTimeout(t);t=setTimeout(()=>{hidden.has(k)?hidden.delete(k):hidden.add(k);draw()},220)};
    b.ondblclick=()=>{clearTimeout(t);hidden.clear();D.channels.forEach((_,j)=>{if(j!==k)hidden.add(j)});draw()};
    L.appendChild(b);
  });
}
function draw(){
  legend();
  const W=D.rows*rw, H=(hi-lo+1)*kh, y=n=>(hi-n)*kh;
  const roll=document.getElementById("roll"),keys=document.getElementById("keys"),ruler=document.getElementById("ruler");
  for(const s of [roll,keys,ruler])s.innerHTML="";
  roll.setAttribute("width",W);roll.setAttribute("height",H);
  keys.setAttribute("width",44);keys.setAttribute("height",H);
  ruler.setAttribute("width",W);ruler.setAttribute("height",22);
  for(let n=lo;n<=hi;n++){
    const blk=BLACK.has(n%12);
    el("rect",{x:0,y:y(n),width:W,height:kh,fill:blk?"var(--black)":"var(--lane)"},roll);
    if(n%12===0)el("line",{x1:0,x2:W,y1:y(n)+kh,y2:y(n)+kh,stroke:"var(--beat)"},roll);
    el("rect",{x:0,y:y(n),width:blk?28:44,height:kh,fill:blk?"#2a2d35":"#c9ccd3",stroke:"#555"},keys);
    if(n%12===0&&kh>=8)el("text",{x:22,y:y(n)+kh-2,class:"keytext"},keys).textContent=nname(n);
  }
  const [ha,hb]=D.highlights;
  for(const o of D.orders){
    for(let r=0;r<o.rows;r++){
      const X=(o.start+r)*rw;
      if(r===0)continue;
      if(hb&&r%hb===0)el("line",{x1:X,x2:X,y1:0,y2:H,stroke:"var(--bar)"},roll);
      else if(ha&&r%ha===0&&rw>=4)el("line",{x1:X,x2:X,y1:0,y2:H,stroke:"var(--grid)"},roll);
    }
    const X=o.start*rw;
    el("line",{x1:X,x2:X,y1:0,y2:H,stroke:"var(--order)","stroke-width":1.5},roll);
    el("line",{x1:X,x2:X,y1:0,y2:22,stroke:"var(--order)"},ruler);
    el("text",{x:X+4,y:15,class:"otext"},ruler).textContent=hex(o.order);
    if(o.rows*rw>60){const s=el("text",{x:X+24,y:15,class:"keytext"},ruler);s.textContent=o.rows+" rows"}
  }
  const g=el("g",{},roll);
  D.notes.forEach((n,i)=>{
    if(hidden.has(n.c))return;
    const w=Math.max(n.len*rw-1,2);
    el("rect",{x:n.x*rw,y:y(n.n)+1,width:w,height:Math.max(kh-2,2),rx:2,fill:D.channels[n.c].color,class:"note","data-i":i,"data-n":n.n},g);
    if(w>=36&&kh>=9)el("text",{x:n.x*rw+10,y:y(n.n)+kh-2,class:"nlabel"},g).textContent=n.name;
  });
  D.marks.forEach((m,i)=>{
    if(hidden.has(m.c)||m.n===null)return;
    const cx=m.x*rw+Math.min(rw/2,4), cy=y(m.n)+kh/2, r=Math.max(2,Math.min(kh/3,4));
    el("path",{d:`M${cx} ${cy-r}L${cx+r} ${cy}L${cx} ${cy+r}L${cx-r} ${cy}Z`,class:"mark","data-m":i},g);
  });
  const first=D.notes.find(n=>!hidden.has(n.c));
  if(first&&!draw.scrolled){draw.scrolled=1;const w=document.getElementById("wrap");w.scrollTop=Math.max(0,y(first.n)-w.clientHeight/2)}
}
const tip=document.getElementById("tip");
document.getElementById("roll").addEventListener("mousemove",e=>{
  const t=e.target;let s=null;
  document.querySelectorAll(".note.same").forEach(x=>x.classList.remove("same"));
  if(t.dataset.i!==undefined){
    const n=D.notes[+t.dataset.i],c=D.channels[n.c];
    s=`${n.name}  ${c.label} (ch ${c.ch})\norder:row ${n.at}   ${n.len} row${n.len===1?"":"s"}\ninstrument ${hex(n.ins)}${n.insName?" "+n.insName:""}\n${n.cell}`;
    document.querySelectorAll(`.note[data-n="${n.n}"]`).forEach(x=>x.classList.add("same"));
  }else if(t.dataset.m!==undefined){
    const m=D.marks[+t.dataset.m],c=D.channels[m.c];
    s=`${m.what}\n${c.label} (ch ${c.ch})  order:row ${m.at}\n${m.cell}`;
  }
  if(s){tip.textContent=s;tip.style.display="block";tip.style.left=Math.min(e.clientX+14,innerWidth-tip.offsetWidth-8)+"px";tip.style.top=(e.clientY+14)+"px"}
  else tip.style.display="none";
});
document.getElementById("roll").addEventListener("mouseleave",()=>{tip.style.display="none"});
document.getElementById("zoom").oninput=e=>{rw=+e.target.value;draw()};
document.getElementById("kh").oninput=e=>{kh=+e.target.value;draw()};
draw();
</script></body></html>
"""


def _orders(text):
    if "-" in text:
        a, b = text.split("-")
        return int(a, 16), int(b, 16)
    return int(text, 16), int(text, 16)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Draw a song as a read-only piano roll (HTML).")
    ap.add_argument("song", help="any song furnace can open (.fur, .json, .dmf, ...)")
    ap.add_argument("-o", "--output", help="HTML file to write (default: next to the song)")
    ap.add_argument("--orders", help="order range in hex, e.g. 0-3 (default: the whole song)")
    ap.add_argument("--channels", help="channels, e.g. 0,2 or 0-3 (default: all)")
    ap.add_argument("--subsong", type=int, default=0)
    a = ap.parse_args(argv)
    start, end = _orders(a.orders) if a.orders else (0, None)
    out = Path(a.output) if a.output else Path(a.song).with_suffix(".roll.html")
    data = write(fsong.load(a.song), out, sub_index=a.subsong, order_start=start,
                 order_end=end, channels=a.channels)
    print(f"wrote {out.resolve()}: {len(data['notes'])} notes, {len(data['orders'])} orders, "
          f"{len(data['channels'])} channels")


if __name__ == "__main__":
    main()
