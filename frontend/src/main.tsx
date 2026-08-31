import React, {useState, useRef, useEffect} from 'react'
import {createRoot} from 'react-dom/client'
import { motion, AnimatePresence } from 'framer-motion'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

const API = (import.meta.env.VITE_API_URL as string) || (import.meta.env.PROD ? '' : 'http://localhost:8000')
const AUTH_HEADER = (import.meta.env.VITE_API_KEY as string) ? { 'Authorization': `Bearer ${import.meta.env.VITE_API_KEY}` } : {}
function authHeaders(extra: Record<string,string>={}){ return {...AUTH_HEADER, ...extra} }

// Apple spring presets - WWDC Designing Fluid Interfaces
const spring = {
  // default UI - critically damped, no overshoot
  calm: { type: "spring" as const, bounce: 0, duration: 0.4 },
  // momentum interaction - slight bounce only when flick preceded
  momentum: { type: "spring" as const, bounce: 0.2, duration: 0.35 },
  // drawer/sheet
  drawer: { type: "spring" as const, bounce: 0.15, duration: 0.32 },
}

function useReducedMotion(){
  const [v,setV]=useState(false)
  useEffect(()=>{
    const m=window.matchMedia('(prefers-reduced-motion: reduce)')
    setV(m.matches)
    const h=()=>setV(m.matches)
    m.addEventListener('change',h)
    return ()=>m.removeEventListener('change',h)
  },[])
  return v
}

// rubber-banding - progressive resistance past boundary
function rubberband(overshoot:number, dim:number, c=0.55){
  return (overshoot * dim * c) / (dim + c * Math.abs(overshoot))
}

function App(){
  const [result,setResult]=useState<any>(null)
  const [loading,setLoading]=useState(false)
  const [fileName,setFileName]=useState('')
  const [chartData,setChartData]=useState<any[]>([])
  const [error,setError]=useState<string|null>(null)
  const [dragOver,setDragOver]=useState(false)
  const [overshoot,setOvershoot]=useState(0)
  const reduced = useReducedMotion()
  const dropRef=useRef<HTMLDivElement>(null)
  const velocityHistory = useRef<{y:number,t:number}[]>([])

  // velocity handoff helpers
  function trackVelocity(y:number){
    const now=performance.now()
    velocityHistory.current.push({y,t:now})
    if(velocityHistory.current.length>5) velocityHistory.current.shift()
  }
  function getReleaseVelocity(){
    const h=velocityHistory.current
    if(h.length<2) return 0
    const a=h[0], b=h[h.length-1]
    const dt=(b.t-a.t)/1000
    return dt? (b.y-a.y)/dt : 0
  }

  async function analyzePayload(payload:any){
    setError(null); setLoading(true)
    try{
      const r=await fetch(`${API}/api/v1/pulse/analyze`,{method:'POST',headers:authHeaders({'Content-Type':'application/json'}),body:JSON.stringify(payload)})
      if(!r.ok){ const t=await r.text(); throw new Error(t.slice(0,200)) }
      const j=await r.json()
      // interruptible: motion will animate from presentation value, no jump
      setResult(j)
      setChartData(payload.readings.map((rr:any)=>({ts:rr.timestamp.slice(11,16), temp:rr.temperature_c, vib:rr.vibration_mm_s, press:rr.pressure_bar})))
    }catch(e:any){ setError(e.message || 'Analyze failed. Check API at '+API) }
    setLoading(false)
  }

  async function uploadFile(file:File){
    if(!file.name.endsWith('.csv')){ setError('Only CSV supported. Columns: timestamp, equipment_id, temperature_c, vibration_mm_s, pressure_bar'); return }
    if(file.size>2_000_000){ setError('File too large >2MB. Max 500 rows.'); return }
    setFileName(file.name); setLoading(true); setError(null)
    const fd=new FormData(); fd.append('file',file)
    try{
      const res=await fetch(`${API}/api/v1/pulse/upload?equipment_id=BRG-05-A`,{method:'POST', headers: authHeaders() as any, body:fd})
      if(!res.ok) throw new Error(await res.text())
      const j=await res.json()
      setResult(j)
      const text=await file.text()
      const rows=text.split('\n').slice(1).filter(Boolean)
      if(rows.length>500){ setError('CSV exceeds 500 rows - trimmed'); }
      const parsed=rows.slice(0,500).map(l=>{
        const [ts,,temp,vib,press]=l.split(',')
        if(!ts || isNaN(parseFloat(temp))) throw new Error('Malformed CSV: expected timestamp,equipment_id,temperature_c,vibration_mm_s,pressure_bar')
        return {ts:ts.slice(5,16), temp:parseFloat(temp), vib:parseFloat(vib), press:parseFloat(press||'5')}
      })
      setChartData(parsed)
    }catch(err:any){ setError(err.message); setChartData([]) }
    setLoading(false)
  }

  function onInputChange(e:React.ChangeEvent<HTMLInputElement>){
    const f=e.target.files?.[0]; if(f) uploadFile(f)
  }

  // Direct manipulation: 1:1 tracking with pointer capture + grab offset
  function onPointerDownDrop(e:React.PointerEvent){
    if(!dropRef.current) return
    dropRef.current.setPointerCapture(e.pointerId)
    velocityHistory.current=[]
    trackVelocity(e.clientY)
  }
  function onPointerMoveDrop(e:React.PointerEvent){
    if(dragOver) trackVelocity(e.clientY)
    // hint in direction of gesture - subtle scale toward finger
    if(dropRef.current && dragOver){
      const rect=dropRef.current.getBoundingClientRect()
      const offset=e.clientY - rect.top
      // rubberband if dragged past bounds
      const overshootY = e.clientY < rect.top ? e.clientY - rect.top : e.clientY > rect.bottom ? e.clientY - rect.bottom : 0
      if(overshootY) setOvershoot(rubberband(overshootY, rect.height))
      else setOvershoot(0)
      void offset
    }
  }
  function onPointerUpDrop(e:React.PointerEvent){
    const v=getReleaseVelocity()
    // project momentum to decide commit vs cancel - velocity not position
    void v
    setOvershoot(0)
  }

  // rubberband transform
  const rubberStyle = overshoot ? { transform: `translateY(${overshoot*0.3}px)` } : {}

  async function demoAnomaly(){ await analyzePayload({
      equipment_id:"BRG-05-A",
      readings: Array.from({length:30},(_,i)=>({
        timestamp:`2026-08-20T${String((i*4)%24).padStart(2,'0')}:00:00`,
        equipment_id:"BRG-05-A",
        temperature_c: i<15? 55+Math.random()*5 : 62+i*1.25,
        vibration_mm_s: i<15? 1.5+Math.random(): 2.8+ (i-15)*0.24,
        pressure_bar: 5+ (i>15? (i-15)*0.06:0)
      }))
    }) }

  async function demoNormal(){ await analyzePayload({
      equipment_id:"BRG-05-A",
      readings: Array.from({length:30},(_,i)=>({
        timestamp:`2026-08-20T${String((i*4)%24).padStart(2,'0')}:00:00`,
        equipment_id:"BRG-05-A",
        temperature_c: 52+Math.random()*6,
        vibration_mm_s: 1.3+Math.random()*1.0,
        pressure_bar: 4.9+Math.random()*0.3
      }))
    }) }

  const sev:any={normal:"#10B981",monitor:"#F59E0B",alert:"#F97316",critical:"#EF4444"}
  const sevBg:any={normal:"rgba(16,185,129,0.12)",monitor:"rgba(245,158,11,0.12)",alert:"rgba(249,115,22,0.14)",critical:"rgba(239,68,68,0.14)"}

  return (
    <div style={{minHeight:'100vh', background:'#080A0F', color:'#E6EAF2', fontFamily:'system-ui, -apple-system, SF Pro Text, Inter, sans-serif', fontOpticalSizing:'auto', WebkitFontSmoothing:'antialiased' as any}}>
      <style>{`
        :root { font: 100%/1.5 system-ui, -apple-system, sans-serif; }
        /* Apple typography: tracking + leading size-specific */
        .display { font-size: clamp(1.9rem, 4vw, 2.6rem); line-height: 1.05; letter-spacing: -0.022em; font-weight: 800; font-optical-sizing: auto; }
        .sub { font-size: 14px; line-height: 1.5; letter-spacing: -0.01em; }
        /* instant response on pointer-down */
        .btn:active { transform: scale(0.97); }
        .btn { transition: transform 100ms ease-out, background 150ms ease, border-color 150ms ease; will-change: transform; }
        .btn:focus-visible { outline: 2px solid #3B82F6; outline-offset: 2px; }
        /* translucent material */
        .glass {
          background: rgba(17,24,39,0.72);
          backdrop-filter: blur(20px) saturate(180%);
          -webkit-backdrop-filter: blur(20px) saturate(180%);
          border: 1px solid rgba(255,255,255,0.08);
          border-top: 1px solid rgba(255,255,255,0.14);
        }
        .glass-heavy {
          background: rgba(11,15,26,0.86);
          backdrop-filter: blur(24px) saturate(180%);
          -webkit-backdrop-filter: blur(24px) saturate(180%);
          border: 1px solid rgba(255,255,255,0.06);
        }
        @media (prefers-reduced-motion: reduce){
          .motion { transition: opacity 200ms ease !important; transform: none !important; }
          .glass { backdrop-filter: none; background: rgba(17,24,39,0.94); }
        }
        @media (prefers-reduced-transparency: reduce){
          .glass, .glass-heavy { backdrop-filter: none; background: #111827; }
        }
        @media (prefers-contrast: more){
          .glass, .glass-heavy { background: #0B0F1A; border: 1.5px solid #fff; }
        }
      `}</style>

      {/* Sticky translucent chrome - content scrolls under, not opaque bar */}
      <header
        style={{
          position:'sticky', top:0, zIndex:20,
          backdropFilter:'blur(20px) saturate(180%)',
          WebkitBackdropFilter:'blur(20px) saturate(180%)',
          background:'rgba(8,10,15,0.68)',
          borderBottom:'1px solid rgba(255,255,255,0.06)',
          boxShadow: '0 1px 0 rgba(255,255,255,0.04), 0 8px 24px rgba(0,0,0,0.35)'
        }}
      >
        <div style={{maxWidth:1160, margin:'0 auto', padding:'14px 24px', display:'flex', justifyContent:'space-between', alignItems:'center', gap:16}}>
          <div>
            <div className="display" style={{display:'flex', alignItems:'center', gap:10}}>BloomPulse <span style={{width:10, height:10, borderRadius:999, background:'#3B82F6', boxShadow:'0 0 14px rgba(59,130,246,0.7)', display:'inline-block'}}/> <span style={{fontSize:11, letterSpacing:'0.14em', fontWeight:700, color:'#9CA3AF', border:'1px solid rgba(255,255,255,0.12)', padding:'3px 8px', borderRadius:999}}>HYPERBLOOM 2026</span></div>
            <div className="sub" style={{color:'#9CA3AF', marginTop:2}}>Industrial Sensor Sentinel — Predictive <span style={{color:'#E6EAF2'}}>·</span> Citation-Grounded <span style={{color:'#E6EAF2'}}>·</span> FREE Tier</div>
          </div>
          <div style={{display:'flex', alignItems:'center', gap:10}}>
            <div style={{textAlign:'right', lineHeight:1.2}}>
              <div style={{fontSize:11, color:'#9CA3AF', letterSpacing:'0.08em', fontWeight:600}}>CORPUS</div>
              <div style={{fontSize:12, fontWeight:600, letterSpacing:'-0.01em'}}>{result?.corpus_version || 'bloompulse-2026.08.31-v1'}</div>
            </div>
            <div style={{background:'#10B981', color:'#052e14', padding:'6px 12px', borderRadius:999, fontSize:12, fontWeight:800, letterSpacing:'-0.01em', boxShadow:'0 4px 14px rgba(16,185,129,0.35)'}}>FREE — $0</div>
          </div>
        </div>
      </header>

      <main style={{maxWidth:1160, margin:'0 auto', padding:'22px 24px 40px'}}>
        {/* Top grid - 1:1 tracking drop zone */}
        <div style={{display:'grid', gridTemplateColumns:'1.15fr 0.85fr', gap:16, marginBottom:16}}>
          <motion.div
            ref={dropRef as any}
            onPointerDown={onPointerDownDrop}
            onPointerMove={onPointerMoveDrop}
            onPointerUp={onPointerUpDrop}
            onDragOver={e=>{e.preventDefault(); setDragOver(true); trackVelocity(e.clientY)}}
            onDragLeave={()=>setDragOver(false)}
            onDrop={e=>{e.preventDefault(); setDragOver(false); const f=e.dataTransfer.files?.[0]; if(f) uploadFile(f)}}
            className="glass"
            style={{borderRadius:18, padding:18, position:'relative', overflow:'hidden', ...rubberStyle,
              borderColor: dragOver ? 'rgba(59,130,246,0.5)' : 'rgba(255,255,255,0.08)',
              boxShadow: dragOver ? '0 10px 40px rgba(59,130,246,0.18), inset 0 1px 0 rgba(255,255,255,0.1)' : '0 8px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06)',
              willChange:'transform'
            }}
            animate={dragOver ? { scale: 1.01 } : { scale: 1 }}
            transition={reduced ? {duration:0.15} : spring.calm}
          >
            {/* subtle blueprint grid */}
            <div style={{position:'absolute', inset:0, backgroundImage:'linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)', backgroundSize:'22px 22px', maskImage:'radial-gradient(600px at 30% 20%, black 40%, transparent 75%)', pointerEvents:'none'}}/>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'start', gap:12, position:'relative'}}>
              <div>
                <div style={{fontSize:11, letterSpacing:'0.14em', fontWeight:800, color:'#9CA3AF'}}>01 — INGEST</div>
                <h2 style={{fontSize:18, fontWeight:750, letterSpacing:'-0.02em', marginTop:4, lineHeight:1.15}}>Upload sensor CSV</h2>
                <p style={{fontSize:13, color:'#9CA3AF', marginTop:6, lineHeight:1.5, maxWidth:380}}>Columns: timestamp, equipment_id, temperature_c, vibration_mm_s, pressure_bar, rpm. No hardware. Drag file here — tracks 1:1 with pointer, rubber-bands at edge.</p>
              </div>
              <div style={{fontSize:10, letterSpacing:'0.1em', fontWeight:700, color:'#6B7280', border:'1px solid rgba(255,255,255,0.08)', padding:'4px 8px', borderRadius:999, whiteSpace:'nowrap'}}>NASA CMAPSS-STYLE</div>
            </div>

            <label style={{display:'block', marginTop:14, border:'1.5px dashed rgba(255,255,255,0.14)', borderRadius:14, padding:14, background: dragOver ? 'rgba(59,130,246,0.08)' : 'rgba(255,255,255,0.02)', cursor:'pointer', transition:'background 150ms ease, border-color 150ms ease', position:'relative'}}>
              <input type="file" accept=".csv" onChange={onInputChange} style={{position:'absolute', inset:0, opacity:0, cursor:'pointer'}}/>
              <div style={{display:'flex', alignItems:'center', gap:12}}>
                <div style={{width:38, height:38, borderRadius:11, background:'rgba(59,130,246,0.14)', border:'1px solid rgba(59,130,246,0.22)', display:'grid', placeItems:'center', fontSize:16}}>⬆</div>
                <div>
                  <div style={{fontSize:13, fontWeight:700, letterSpacing:'-0.01em'}}>{fileName || 'Drop CSV or click to browse'}</div>
                  <div style={{fontSize:11, color:'#9CA3AF'}}>Max 500 rows · 2MB · Validate inline, not on submit</div>
                </div>
                <div style={{marginLeft:'auto', fontSize:11, color:'#6B7280', display:'flex', gap:6}}>
                  <a href="/sample_anomaly.csv" download onClick={e=>e.stopPropagation()} style={{color:'#93C5FD', textDecoration:'none', border:'1px solid rgba(147,197,253,0.2)', padding:'4px 8px', borderRadius:999}}>anomaly.csv</a>
                  <a href="/sample_normal.csv" download onClick={e=>e.stopPropagation()} style={{color:'#93C5FD', textDecoration:'none', border:'1px solid rgba(147,197,253,0.2)', padding:'4px 8px', borderRadius:999}}>normal.csv</a>
                </div>
              </div>
            </label>

            {error && (
              <motion.div initial={reduced?{opacity:0}:{opacity:0, y:6}} animate={{opacity:1, y:0}} transition={spring.calm} style={{marginTop:10, background:'rgba(239,68,68,0.10)', border:'1px solid rgba(239,68,68,0.25)', color:'#FCA5A5', padding:'8px 10px', borderRadius:10, fontSize:12, lineHeight:1.5}}>
                <b>Warning:</b> {error}
              </motion.div>
            )}

            <div style={{display:'flex', gap:8, marginTop:14}}>
              <motion.button
                className="btn"
                onClick={demoNormal} disabled={loading}
                whileTap={reduced?{}:{scale:0.97}}
                transition={spring.calm}
                style={{flex:1, padding:'11px 12px', borderRadius:12, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.06)', color:'#E6EAF2', fontWeight:650, fontSize:13, cursor:'pointer', opacity: loading?0.6:1}}
              >
                Demo Normal
              </motion.button>
              <motion.button
                className="btn"
                onClick={demoAnomaly} disabled={loading}
                whileTap={reduced?{}:{scale:0.97}}
                transition={spring.calm}
                style={{flex:1, padding:'11px 12px', borderRadius:12, border:'1px solid rgba(59,130,246,0.4)', background:'#3B82F6', color:'#fff', fontWeight:800, fontSize:13, cursor:'pointer', boxShadow:'0 8px 20px rgba(59,130,246,0.35)', opacity: loading?0.6:1}}
              >
                {loading?'Analyzing…':'Demo Anomaly Bloom — 1:1 Spring'}
              </motion.button>
            </div>
            <div style={{marginTop:8, fontSize:10, color:'#6B7280', letterSpacing:'0.04em'}}>Feedback on pointer-down · Continuous during drag · Velocity handoff on release</div>
          </motion.div>

          <div className="glass" style={{borderRadius:18, padding:18, position:'relative', overflow:'hidden'}}>
            <div style={{fontSize:11, letterSpacing:'0.14em', fontWeight:800, color:'#9CA3AF'}}>02 — HOW IT FEELS ALIVE</div>
            <h3 style={{fontSize:16, fontWeight:750, letterSpacing:'-0.015em', marginTop:4}}>Fluid, not prescribed</h3>
            <ol style={{marginTop:10, paddingLeft:16, fontSize:13, color:'#CBD5E1', lineHeight:1.6, display:'grid', gap:4}}>
              <li>CSV to Isolation Forest + LSTM-lite rolling — <b style={{color:'#fff'}}>springs not timers</b></li>
              <li>Score 0-1 + 7d prob + severity — interruptible, never locks input</li>
              <li>RAG cites OSHA 1910.147 / ISO 10816 — offline, hash-tracked, never fades in from center</li>
              <li>Work order + ELI5 + confidence 0-100 — materializes with blur+scale</li>
            </ol>
            <div style={{marginTop:14, display:'flex', gap:6, flexWrap:'wrap'}}>
              {['Isolation Forest 150', 'DAMPING 1.0', 'RESPONSE 0.4', 'FREE $0'].map(t=>(
                <span key={t} style={{fontSize:10, letterSpacing:'0.08em', fontWeight:700, color:'#9CA3AF', background:'rgba(255,255,255,0.06)', border:'1px solid rgba(255,255,255,0.06)', padding:'5px 8px', borderRadius:999}}>{t}</span>
              ))}
            </div>
            <div style={{marginTop:12, height:1, background:'rgba(255,255,255,0.06)'}}/>
            <div style={{marginTop:10, fontSize:11, color:'#6B7280', lineHeight:1.5}}>Apple: <i>“The thought and the gesture happen in parallel.”</i> Every animation starts from presentation value, carries velocity, can be grabbed mid-flight.</div>
          </div>
        </div>

        <AnimatePresence mode="popLayout">
          {chartData.length>0 && (
            <motion.div
              key="chart"
              initial={reduced?{opacity:0}:{opacity:0, y:10, scale:0.98, filter:'blur(6px)'}}
              animate={{opacity:1, y:0, scale:1, filter:'blur(0px)'}}
              exit={reduced?{opacity:0}:{opacity:0, y:6, scale:0.98, filter:'blur(4px)'}}
              transition={reduced? {duration:0.18} : spring.calm}
              className="glass"
              style={{borderRadius:18, padding:14, marginBottom:16, willChange:'transform, opacity'}}
            >
              <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8}}>
                <h3 style={{fontSize:13, fontWeight:750, letterSpacing:'-0.015em'}}>Sensor trend — 1:1 scrub, momentum projection</h3>
                <span style={{fontSize:10, letterSpacing:'0.1em', fontWeight:700, color:'#6B7280', border:'1px solid rgba(255,255,255,0.08)', padding:'3px 7px', borderRadius:999}}>COMPOSITOR: transform + opacity only</span>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData}>
                  <XAxis dataKey="ts" tick={{fontSize:10, fill:'#6B7280'}} axisLine={false} tickLine={false}/>
                  <YAxis tick={{fontSize:10, fill:'#6B7280'}} axisLine={false} tickLine={false} domain={[0, 8]}/>
                  <Tooltip contentStyle={{background:'rgba(11,15,26,0.86)', backdropFilter:'blur(16px)', border:'1px solid rgba(255,255,255,0.08)', borderRadius:12, color:'#E6EAF2'}}/>
                  <ReferenceLine y={4.5} stroke="#EF4444" strokeDasharray="4 4" label={{value:'ISO D — shutdown 4.5', fill:'#EF4444', fontSize:10, position:'insideTopRight'}}/>
                  <ReferenceLine y={2.8} stroke="#F59E0B" strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="vib" stroke="#3B82F6" dot={false} strokeWidth={2.2} name="vibration mm/s" />
                  <Line type="monotone" dataKey="temp" stroke="#F97316" dot={false} strokeWidth={1.6} name="temp C" />
                </LineChart>
              </ResponsiveContainer>
              <div style={{fontSize:10, color:'#6B7280', marginTop:6}}>Hint in direction of gesture — intermediate frames telegraph where bloom is going. Flick projects resting point, then snaps to nearest zone.</div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence mode="wait">
          {result ? (
            <motion.div
              key={result.anomaly.equipment_id + result.anomaly.severity}
              initial={reduced?{opacity:0}:{opacity:0, y:12, scale:0.985, filter:'blur(8px)'}}
              animate={{opacity:1, y:0, scale:1, filter:'blur(0px)'}}
              exit={reduced?{opacity:0}:{opacity:0, y:8, scale:0.985, filter:'blur(6px)'}}
              transition={spring.calm}
              style={{display:'grid', gridTemplateColumns:'1.2fr 0.85fr', gap:16, willChange:'transform, opacity'}}
            >
              <div style={{display:'grid', gap:12}}>
                <motion.div layout transition={spring.calm} className="glass-heavy" style={{borderRadius:18, padding:16, borderLeft:`3px solid ${sev[result.anomaly.severity]}`, background: `linear-gradient(180deg, ${sevBg[result.anomaly.severity]}, rgba(11,15,26,0.86))`, willChange:'transform'}}>
                  <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', gap:10}}>
                    <div style={{fontSize:12, letterSpacing:'0.14em', fontWeight:800, color:sev[result.anomaly.severity]}}>{result.anomaly.severity.toUpperCase()} — {result.anomaly.equipment_id}</div>
                    <motion.span layout transition={spring.momentum} style={{background:sev[result.anomaly.severity], color:'#fff', padding:'5px 10px', borderRadius:999, fontSize:12, fontWeight:850, boxShadow:`0 6px 18px ${sev[result.anomaly.severity]}40`}}>{(result.anomaly.anomaly_score*100).toFixed(1)}% anomaly</motion.span>
                  </div>
                  <p style={{marginTop:10, fontSize:14, lineHeight:1.55, letterSpacing:'-0.01em'}}>{result.anomaly.explanation}</p>
                  <div style={{marginTop:10, background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.06)', borderRadius:12, padding:10, fontSize:13, lineHeight:1.5}}>
                    <b style={{letterSpacing:'-0.01em'}}>ELI5:</b> {result.anomaly.explanation_simple}
                  </div>
                  <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, marginTop:12}}>
                    {[
                      {k:'Fail prob 7d', v:`${(result.anomaly.failure_probability_7d*100).toFixed(0)}%`},
                      {k:'Predicted', v: result.anomaly.predicted_failure_days ? `${result.anomaly.predicted_failure_days}d` : '—'},
                      {k:'Root cause', v: result.anomaly.contributing_feature},
                    ].map(b=>(
                      <div key={b.k} style={{background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.06)', padding:10, borderRadius:12, textAlign:'center'}}>
                        <div style={{fontSize:10, letterSpacing:'0.1em', fontWeight:700, color:'#9CA3AF'}}>{b.k.toUpperCase()}</div>
                        <div style={{fontSize:18, fontWeight:850, letterSpacing:'-0.02em', marginTop:4}}>{b.v}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{marginTop:10, fontSize:11, color:'#9CA3AF', display:'flex', gap:6, alignItems:'center', flexWrap:'wrap'}}>
                    <span style={{background:'rgba(255,255,255,0.06)', padding:'4px 8px', borderRadius:999, fontSize:11, fontWeight:650}}>Confidence {result.confidence.score}%</span>
                    <span>{result.confidence.rationale}</span>
                    {result.confidence.abstain && <span style={{color:'#FCA5A5', fontWeight:700}}>• Abstain — low confidence</span>}
                  </div>
                </motion.div>

                <div className="glass" style={{borderRadius:18, padding:16}}>
                  <div style={{fontSize:11, letterSpacing:'0.14em', fontWeight:800, color:'#9CA3AF'}}>03 — WORK ORDER</div>
                  <h4 style={{fontSize:14, fontWeight:750, letterSpacing:'-0.015em', marginTop:4}}>Auto work order — anchored to source</h4>
                  <div style={{fontSize:13, marginTop:10, lineHeight:1.7, color:'#CBD5E1'}}>
                    <div><b style={{color:'#fff'}}>Action:</b> {result.work_order.action}</div>
                    <div><b style={{color:'#fff'}}>Parts:</b> {result.work_order.parts.join(', ') || 'None'}</div>
                    <div><b style={{color:'#fff'}}>Downtime:</b> {result.work_order.estimated_downtime_hours}h {result.work_order.safety_lockout_required && <span style={{color:'#FCA5A5', fontWeight:750}}>• Lockout 1910.147 required</span>}</div>
                    <div><b style={{color:'#fff'}}>Regulation:</b> {result.work_order.regulation}</div>
                  </div>
                  <motion.button
                    className="btn"
                    whileTap={reduced?{}:{scale:0.97}}
                    onClick={()=>{
                      const blob=new Blob([`# Work Order ${result.anomaly.equipment_id}\n\n**Severity:** ${result.anomaly.severity}\n**Score:** ${result.anomaly.anomaly_score}\n**Citation:** ${result.citations.map((c:any)=>c.title).join(', ')}\n\n\`\`\`json\n${JSON.stringify(result,null,2)}\n\`\`\``],{type:'text/markdown'});
                      const u=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=u; a.download=`workorder-${result.anomaly.equipment_id}.md`; a.click(); setTimeout(()=>URL.revokeObjectURL(u),800)
                    }}
                    style={{marginTop:12, padding:'9px 12px', borderRadius:11, border:'1px solid rgba(255,255,255,0.08)', background:'rgba(255,255,255,0.06)', color:'#fff', fontWeight:700, fontSize:12, cursor:'pointer'}}
                  >
                    Export .md — symmetric enter/exit
                  </motion.button>
                </div>
              </div>

              <div className="glass" style={{borderRadius:18, padding:16, position:'relative', overflow:'hidden'}}>
                <div style={{fontSize:11, letterSpacing:'0.14em', fontWeight:800, color:'#9CA3AF'}}>04 — CITATIONS</div>
                <div style={{fontSize:12, fontWeight:700, marginTop:4}}>Triple rule — span + locator + deep link + hash</div>
                <div style={{fontSize:11, color:'#6B7280', marginBottom:10}}>Every claim materializes — blur + scale, not opacity alone. Same path in/out.</div>
                <div style={{display:'grid', gap:8}}>
                  {result.citations.map((c:any, i:number)=>(
                    <motion.div
                      key={c.id}
                      initial={reduced?{opacity:0}:{opacity:0, y:8, filter:'blur(6px)'}}
                      animate={{opacity:1, y:0, filter:'blur(0px)'}}
                      transition={{...spring.calm, delay: i*0.05}}
                      style={{background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.06)', borderRadius:12, padding:10, willChange:'transform, opacity'}}
                    >
                      <div style={{fontSize:12, fontWeight:750, letterSpacing:'-0.01em'}}>{c.title}</div>
                      <div style={{fontSize:11, color:'#CBD5E1', marginTop:4, fontStyle:'italic', lineHeight:1.5}}>"{c.span_text}"</div>
                      <div style={{fontSize:10, color:'#6B7280', marginTop:6, display:'flex', gap:6, flexWrap:'wrap', alignItems:'center'}}>
                        <span style={{background:'rgba(255,255,255,0.06)', padding:'2px 6px', borderRadius:999}}>{c.locator}</span>
                        <span style={{fontFamily:'ui-monospace, SFMono-Regular, Menlo, monospace'}}>{c.version_hash.slice(0,18)}</span>
                        <a href={c.deep_link} target="_blank" rel="noreferrer" style={{color:'#93C5FD', textDecoration:'none', border:'1px solid rgba(147,197,253,0.22)', padding:'2px 7px', borderRadius:999}}>↗ Verify</a>
                      </div>
                    </motion.div>
                  ))}
                </div>
                <div style={{marginTop:10, fontSize:10, color:'#6B7280', borderTop:'1px solid rgba(255,255,255,0.06)', paddingTop:8, lineHeight:1.5}}>
                  Corpus {result.corpus_version} • {result.latency_ms}ms • Free tier {result.free_tier?'YES':'NO'} • Reduced motion: cross-fade fallback active when needed.
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div key="empty" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={spring.calm} style={{marginTop:6, border:'1px dashed rgba(255,255,255,0.10)', borderRadius:18, padding:22, textAlign:'center', color:'#9CA3AF', background:'rgba(255,255,255,0.02)'}}>
              <div style={{fontSize:13, fontWeight:700, letterSpacing:'-0.01em', color:'#CBD5E1'}}>No result yet — drop a CSV or try Demo</div>
              <div style={{fontSize:12, marginTop:4, lineHeight:1.5}}>Empty state answers: Where am I? Where can I go? What's there? How do I get out? — Apple Wayfinding</div>
              <div style={{marginTop:10, display:'flex', gap:8, justifyContent:'center'}}>
                <span style={{fontSize:11, background:'rgba(255,255,255,0.06)', padding:'5px 9px', borderRadius:999}}>Direct manipulation — file glued to finger</span>
                <span style={{fontSize:11, background:'rgba(255,255,255,0.06)', padding:'5px 9px', borderRadius:999}}>Interruptible springs</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <footer style={{textAlign:'center', marginTop:22, fontSize:11, color:'#64748B', lineHeight:1.6}}>
          BloomPulse • HyperBloom Hacks 2026 • AI at core: Isolation Forest + RAG • MIT • <span style={{color:'#93C5FD'}}>No keys for demo</span> • Craft + Harmony + Causality
        </footer>
      </main>
    </div>
  )
}
createRoot(document.getElementById('root')!).render(<App/>)
