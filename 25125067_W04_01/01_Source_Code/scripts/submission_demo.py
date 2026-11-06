"""Local evidence viewer for the existing backend. Frozen replay, no live API calls.

Run from source root: python -m uvicorn scripts.submission_demo:app --port 8765
"""
import json
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from exam_baseline.pipeline.bootstrap import replay_providers
from exam_baseline.pipeline.contracts import PipelineRequest
from exam_baseline.pipeline.orchestrator import Orchestrator

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title='ASTRA submission evidence viewer')


@app.post('/run/{case}')
async def run(case: str):
    if case not in {'text_01', 'visual_graph'}:
        raise HTTPException(404)
    folder = ROOT / 'examples/pipeline' / case
    request = PipelineRequest.model_validate_json((folder / 'input.json').read_text('utf-8'))
    output = ROOT.parent / '05_Evidence/demo_runs' / f'{case}_{uuid4().hex[:8]}'
    result = await Orchestrator(replay_providers(folder)).run(request, output)
    source = Path(result.final_latex).read_text('utf-8') if result.final_latex else ''
    (output / 'cli_equivalent_result.json').write_text(result.model_dump_json(indent=2), 'utf-8')
    return {'case': case, 'question_count': request.request.matrix.question_count,
            'result': result.model_dump(mode='json'), 'latex_source': source}


@app.get('/', response_class=HTMLResponse)
def home():
    return HTML


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>ASTRA | Feature evidence</title><style>
*{box-sizing:border-box}body{margin:0;background:#edf1f7;color:#18243a;font:16px Arial,sans-serif}
header{background:#142844;color:white;padding:24px 36px}header p{color:#c7d6e9;margin-bottom:0}
main{padding:25px 36px;max-width:1500px;margin:auto}h1{font-size:27px;margin:0 0 10px}
.notice{background:#fff8e7;border-left:4px solid #d49a2a;padding:13px 17px;line-height:1.5}
button{border:0;border-radius:6px;padding:13px 20px;background:#176879;color:white;font-weight:bold;cursor:pointer;margin:18px 10px 15px 0}
.cards{display:flex;gap:14px}.card{background:white;border-radius:8px;padding:15px;flex:1;box-shadow:0 1px 4px #ccd5e1}
.card small{display:block;color:#62718a;margin-bottom:7px}.card b{font-size:19px}.columns{display:grid;grid-template-columns:1fr 1.35fr;gap:18px;margin-top:20px}
section{background:white;border-radius:8px;padding:18px}h2{font-size:19px;margin:0 0 13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 Consolas,monospace;background:#f3f6fa;padding:14px;border-radius:6px;margin:0}
#trace div{padding:10px 0;border-bottom:1px solid #e3e9f1}#status{font-weight:bold;color:#176879}footer{font-size:13px;color:#60718a;margin:18px 0}
</style><header><h1>ASTRA — Exam generation pipeline</h1><p>Lab04 • 25125067 Nguyen Phu Trong • Composer → Illustrator → Solver → Reviewer</p></header>
<main><div class="notice"><b>Submission evidence viewer.</b> This small local harness invokes the existing Python backend.
 All demonstrations use frozen offline fixtures. They verify integration and artifacts, not live-model quality.</div>
<button onclick="run('text_01')">Run text exam • 4 questions</button><button onclick="run('visual_graph')">Run graph exam • TikZ / PGFPlots</button><span id="status">Ready to run</span>
<div class="cards"><div class="card"><small>EXECUTION</small><b id="execution">—</b></div><div class="card"><small>PROVIDER CALLS</small><b id="calls">—</b></div><div class="card"><small>LATEX VALIDATION</small><b id="validation">—</b></div><div class="card"><small>HUMAN REVIEW</small><b id="human">—</b></div></div>
<div class="columns"><section><h2>Workflow events</h2><div id="trace">No run yet.</div><h2 style="margin-top:22px">Result and independent answers</h2><pre id="result">The Solver receives student content and merged LaTeX source, without the Composer answer key.</pre></section>
<section><h2>Generated de_thi.tex • student artifact</h2><pre id="source">The output source will appear here.</pre></section></div>
<footer>The final exam always remains pending human review. Static checks do not certify PDF compilation or mathematical correctness.</footer></main>
<script>async function run(name){document.querySelector('#status').textContent='Running backend…';try{
 const response=await fetch('/run/'+name,{method:'POST'});if(!response.ok)throw Error('HTTP '+response.status);const d=await response.json(),r=d.result;
 for(const [id,value]of Object.entries({execution:r.execution_status,calls:r.calls.length,validation:r.latex_validation,human:r.human_review_required?'Required':'No'}))document.getElementById(id).textContent=value;
 document.querySelector('#status').textContent='Finished: '+name;
 const trace=document.getElementById('trace');trace.replaceChildren();r.events.forEach(e=>{const x=document.createElement('div');x.textContent='r'+e.revision+' · '+e.stage+' · '+e.status+' — '+e.detail;trace.appendChild(x)});
 document.getElementById('result').textContent=JSON.stringify({case:d.case,questions:d.question_count,quality_decision:r.quality_decision,revision:r.revision,reviewer_feedback_sent:r.reviewer_feedback_sent,review_covers_final_revision:r.review_covers_final_revision,answers:r.solutions?.entries,errors:r.errors},null,2);
 document.getElementById('source').textContent=d.latex_source;
 }catch(e){document.querySelector('#status').textContent='Failed: '+e.message}}</script></html>'''
