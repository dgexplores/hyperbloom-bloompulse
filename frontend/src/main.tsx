import React, {useState} from 'react'
import {createRoot} from 'react-dom/client'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App(){
  const [result,setResult]=useState<any>(null)
  const [loading,setLoading]=useState(false)
  const [fileName,setFileName]=useState('')
  const [chartData,setChartData]=useState<any[]>([])

  async function uploadFile(e:React.ChangeEvent<HTMLInputElement>){
    const f=e.target.files?.[0]
    if(!f) return
    setFileName(f.name)
    setLoading(true)
    const fd=new FormData()
    fd.append('file',f)
    try{
      const res=await fetch(`${API}/api/v1/pulse/upload?equipment_id=BRG-05-A`,{method:'POST',body:fd})
      const j=await res.json()
      setResult(j)
      // build chart from anomaly metrics - mock series from file
      const text=await f.text()
      const rows=text.split('\n').slice(1, -0).filter(Boolean).map(l=>{
        const [ts,,temp,vib,press]=l.split(',')
        return {ts:ts.slice(5,16), temp:parseFloat(temp), vib:parseFloat(vib), press:parseFloat(press)}
      })
      setChartData(rows)
    }catch(err:any){ alert(err.message)}
    setLoading(false)
  }

  async function demoAnomaly(){
    setLoading(true)
    const res=await fetch(`/model/sample_anomaly.csv`).catch(()=>null)
    // fallback: call analyze with synthetic anomaly payload
    const payload={
      equipment_id:"BRG-05-A",
      readings: Array.from({length:30},(_,i)=>({
        timestamp:`2026-08-20T${String((i*4)%24).padStart(2,'0')}:00:00`,
        equipment_id:"BRG-05-A",
        temperature_c: i<15? 55+Math.random()*5 : 62+i*1.1,
        vibration_mm_s: i<15? 1.5+Math.random(): 2.8+ (i-15)*0.22,
        pressure_bar: 5+ (i>15? (i-15)*0.05:0)
      }))
    }
    const r=await fetch(`${API}/api/v1/pulse/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    const j=await r.json()
    setResult(j)
    setChartData(payload.readings.map(r=>({ts:r.timestamp.slice(11,16), temp:r.temperature_c, vib:r.vibration_mm_s, press:r.pressure_bar})))
    setLoading(false)
  }

  async function demoNormal(){
    setLoading(true)
    const payload={
      equipment_id:"BRG-05-A",
      readings: Array.from({length:30},(_,i)=>({
        timestamp:`2026-08-20T${String((i*4)%24).padStart(2,'0')}:00:00`,
        equipment_id:"BRG-05-A",
        temperature_c: 52+Math.random()*6,
        vibration_mm_s: 1.3+Math.random()*1.0,
        pressure_bar: 4.9+Math.random()*0.3
      }))
    }
    const r=await fetch(`${API}/api/v1/pulse/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    const j=await r.json()
    setResult(j)
    setChartData(payload.readings.map(r=>({ts:r.timestamp.slice(11,16), temp:r.temperature_c, vib:r.vibration_mm_s, press:r.pressure_bar})))
    setLoading(false)
  }

  const sevColor:any={normal:"#10B981",monitor:"#F59E0B",alert:"#F97316",critical:"#EF4444"}

  return (
    <div style={{maxWidth:1100, margin:'0 auto', padding:'24px'}}>
      <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:24, borderBottom:'1px solid #1F2937', paddingBottom:16}}>
        <div>
          <h1 style={{fontSize:28, fontWeight:800}}>BloomPulse <span style={{color:'#3B82F6'}}>●</span></h1>
          <p style={{color:'#9CA3AF', fontSize:14}}>Industrial Sensor Sentinel - Predictive + Citation-Grounded - FREE Tier</p>
        </div>
        <div style={{textAlign:'right'}}>
          <div style={{background:'#10B981', color:'#052e1a', padding:'4px 10px', borderRadius:20, fontSize:12, fontWeight:700}}>FREE — ₹0 / $0</div>
          <div style={{fontSize:11, color:'#6B7280', marginTop:4}}>Corpus {result?.corpus_version || 'bloompulse-2026.08.31-v1'}</div>
        </div>
      </header>

      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:20}}>
        <div style={{background:'#111827', border:'1px solid #1F2937', borderRadius:16, padding:16}}>
          <h3 style={{marginBottom:8}}>1. Upload Sensor CSV</h3>
          <p style={{fontSize:12, color:'#9CA3AF', marginBottom:12}}>Columns: timestamp, equipment_id, temperature_c, vibration_mm_s, pressure_bar, rpm. No hardware needed - use sample.</p>
          <input type="file" accept=".csv" onChange={uploadFile} style={{marginBottom:12}}/>
          {fileName && <div style={{fontSize:12, color:'#6B7280'}}>{fileName}</div>}
          <div style={{display:'flex', gap:8, marginTop:12}}>
            <button onClick={demoNormal} disabled={loading} style={{flex:1, padding:'10px', borderRadius:10, border:'none', background:'#1F2937', color:'#fff', cursor:'pointer'}}>Demo Normal (30 rows)</button>
            <button onClick={demoAnomaly} disabled={loading} style={{flex:1, padding:'10px', borderRadius:10, border:'none', background:'#3B82F6', color:'#fff', fontWeight:700, cursor:'pointer'}}>{loading?'Analyzing...':'Demo Anomaly Bloom'}</button>
          </div>
          <div style={{marginTop:12, fontSize:11, color:'#6B7280'}}>Try: <a href="/sample_anomaly.csv" download>sample_anomaly.csv</a> | <a href="/sample_normal.csv" download>sample_normal.csv</a></div>
        </div>
        <div style={{background:'#111827', border:'1px solid #1F2937', borderRadius:16, padding:16}}>
          <h3>How it works</h3>
          <ol style={{fontSize:13, color:'#9CA3AF', marginLeft:16, lineHeight:1.7, marginTop:8}}>
            <li>CSV to Isolation Forest + LSTM-lite rolling features</li>
            <li>Score 0-1 + failure probability 7d + severity</li>
            <li>RAG cites OSHA 1910.147 / ISO 10816-3 / NTN manual - offline, hash-tracked</li>
            <li>Work order + ELI5 + confidence + abstain gate 0.70</li>
          </ol>
          <div style={{marginTop:12, display:'flex', gap:6, flexWrap:'wrap'}}>
            <span style={{background:'#1F2937', padding:'4px 8px', borderRadius:20, fontSize:11}}>Isolation Forest 150 trees</span>
            <span style={{background:'#1F2937', padding:'4px 8px', borderRadius:20, fontSize:11}}>pgvector optional</span>
            <span style={{background:'#1F2937', padding:'4px 8px', borderRadius:20, fontSize:11}}>100% FREE</span>
          </div>
        </div>
      </div>

      {chartData.length>0 && (
        <div style={{background:'#111827', border:'1px solid #1F2937', borderRadius:16, padding:16, marginBottom:16}}>
          <h3 style={{marginBottom:8}}>Sensor Trend (from upload)</h3>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={chartData}>
              <XAxis dataKey="ts" tick={{fontSize:10, fill:'#6B7280'}}/>
              <YAxis tick={{fontSize:10, fill:'#6B7280'}}/>
              <Tooltip contentStyle={{background:'#0B0F1A', border:'1px solid #1F2937'}}/>
              <ReferenceLine y={4.5} stroke="#EF4444" strokeDasharray="4 4" label={{value:'4.5 vib alert', fill:'#EF4444', fontSize:10}}/>
              <ReferenceLine y={2.8} stroke="#F59E0B" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="vib" stroke="#3B82F6" dot={false} strokeWidth={2} name="vibration mm/s"/>
              <Line type="monotone" dataKey="temp" stroke="#F97316" dot={false} strokeWidth={1.5} name="temp C"/>
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {result && (
        <div style={{display:'grid', gridTemplateColumns:'1.2fr 0.8fr', gap:16}}>
          <div>
            <div style={{background:'#111827', border:`2px solid ${sevColor[result.anomaly.severity] || '#1F2937'}`, borderRadius:16, padding:16, marginBottom:12}}>
              <div style={{display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                <h3 style={{color:sevColor[result.anomaly.severity]}}>{result.anomaly.severity.toUpperCase()} - {result.anomaly.equipment_id}</h3>
                <span style={{background:sevColor[result.anomaly.severity], color:'#fff', padding:'4px 10px', borderRadius:20, fontSize:12, fontWeight:800}}>{(result.anomaly.anomaly_score*100).toFixed(1)}% anomaly</span>
              </div>
              <p style={{marginTop:8, fontSize:14, lineHeight:1.5}}>{result.anomaly.explanation}</p>
              <div style={{background:'#0B0F1A', borderRadius:10, padding:10, marginTop:10, fontSize:13, border:'1px solid #1F2937'}}>
                <b>ELI5:</b> {result.anomaly.explanation_simple}
              </div>
              <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, marginTop:12}}>
                <div style={{background:'#0B0F1A', padding:10, borderRadius:10, textAlign:'center'}}><div style={{fontSize:11, color:'#9CA3AF'}}>Fail prob 7d</div><div style={{fontSize:20, fontWeight:800}}>{(result.anomaly.failure_probability_7d*100).toFixed(0)}%</div></div>
                <div style={{background:'#0B0F1A', padding:10, borderRadius:10, textAlign:'center'}}><div style={{fontSize:11, color:'#9CA3AF'}}>Predicted days</div><div style={{fontSize:20, fontWeight:800}}>{result.anomaly.predicted_failure_days ?? '—'}</div></div>
                <div style={{background:'#0B0F1A', padding:10, borderRadius:10, textAlign:'center'}}><div style={{fontSize:11, color:'#9CA3AF'}}>Root cause</div><div style={{fontSize:12, fontWeight:700, marginTop:6}}>{result.anomaly.contributing_feature}</div></div>
              </div>
              <div style={{marginTop:10, fontSize:12, color:'#9CA3AF'}}>Confidence {result.confidence.score}% - {result.confidence.rationale} {result.confidence.abstain && '(Abstain: low confidence)'}</div>
            </div>

            <div style={{background:'#111827', border:'1px solid #1F2937', borderRadius:16, padding:16}}>
              <h4>Work Order (auto)</h4>
              <div style={{fontSize:13, marginTop:8, lineHeight:1.6}}>
                <div><b>Action:</b> {result.work_order.action}</div>
                <div><b>Parts:</b> {result.work_order.parts.join(', ') || 'None'}</div>
                <div><b>Downtime:</b> {result.work_order.estimated_downtime_hours}h {result.work_order.safety_lockout_required && <span style={{color:'#EF4444', fontWeight:700}}>• Lockout 1910.147 required</span>}</div>
                <div><b>Regulation:</b> {result.work_order.regulation}</div>
              </div>
              <button onClick={()=>{const blob=new Blob([`# Work Order ${result.anomaly.equipment_id}\n${JSON.stringify(result,null,2)}`],{type:'text/markdown'}); const u=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=u; a.download=`workorder-${result.anomaly.equipment_id}.md`; a.click()}} style={{marginTop:10, padding:'8px 12px', borderRadius:8, border:'1px solid #374151', background:'#0B0F1A', color:'#fff', cursor:'pointer'}}>Export .md</button>
            </div>
          </div>

          <div style={{background:'#111827', border:'1px solid #1F2937', borderRadius:16, padding:16}}>
            <h4>Citations (triple rule)</h4>
            <div style={{fontSize:11, color:'#6B7280', marginBottom:8}}>Every claim has span + locator + deep link + hash</div>
            {result.citations.map((c:any)=>(
              <div key={c.id} style={{background:'#0B0F1A', border:'1px solid #1F2937', borderRadius:10, padding:10, marginBottom:8}}>
                <div style={{fontSize:12, fontWeight:700}}>{c.title}</div>
                <div style={{fontSize:11, color:'#9CA3AF', marginTop:4, fontStyle:'italic'}}>"{c.span_text}"</div>
                <div style={{fontSize:10, color:'#6B7280', marginTop:4}}>{c.locator} • {c.version_hash.slice(0,18)} • <a href={c.deep_link} target="_blank">↗ Verify</a></div>
              </div>
            ))}
            <div style={{marginTop:8, fontSize:10, color:'#6B7280', borderTop:'1px solid #1F2937', paddingTop:8}}>
              Corpus {result.corpus_version} • Latency {result.latency_ms}ms • Free tier {result.free_tier?'YES':'NO - paid path'} • Information only — not a substitute for certified inspection.
            </div>
          </div>
        </div>
      )}

      <footer style={{textAlign:'center', marginTop:24, fontSize:11, color:'#4B5563'}}>
        BloomPulse • HyperBloom Hacks 2026 • AI at core: Isolation Forest + LLM RAG • MIT • No keys needed for demo
      </footer>
    </div>
  )
}
createRoot(document.getElementById('root')!).render(<App/>)
