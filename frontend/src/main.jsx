import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

function useRoute() {
  const [route, setRoute] = useState(window.location.hash || "#/");
  useEffect(() => {
    const onChange = () => setRoute(window.location.hash || "#/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

function go(path) {
  window.location.hash = path;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}`;
}

function TopNav({ route, me, onLogout }) {
  return (
    <div class="topbar">
      <nav class="nav">
        <button
          class={route === "#/" ? "navbtn active" : "navbtn"}
          onClick={() => go("/")}
        >
          环盆作业台
        </button>
        <button
          class={route === "#/tickets" ? "navbtn active" : "navbtn"}
          onClick={() => go("/tickets")}
        >
          渗透单
        </button>
      </nav>
      <div class="nav-right">
        {me && (
          <span class="who">
            {me.username}（{me.role === "admin" ? "管理员" : "缫丝工"}）
          </span>
        )}
        <button onClick={onLogout}>退出</button>
      </div>
    </div>
  );
}

function Login({ onOk }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("123456");
  const [err, setErr] = useState("");
  async function submit(e) {
    e.preventDefault();
    setErr("");
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      onOk();
    } catch (ex) {
      setErr(ex.message);
    }
  }
  return (
    <div class="login">
      <h1>江口缫丝坞</h1>
      <p>汤温环盆作业台，不是列表台账。</p>
      <form onSubmit={submit} autocomplete="off">
        <label>
          用户名
          <input
            name="username"
            autocomplete="off"
            value={username}
            onInput={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          密码
          <input
            name="password"
            type="password"
            autocomplete="off"
            value={password}
            onInput={(e) => setPassword(e.target.value)}
          />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function Yard({ me, onLogout }) {
  const route = useRoute();
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    setPicked((prev) =>
      prev ? data.basins.find((b) => b.id === prev.id) || data.basins[0] : prev
    );
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div class="yard">
        <TopNav route={route} me={me} onLogout={onLogout} />
        {err || "装载环盆…"}
      </div>
    );
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await refresh();
    } catch (ex) {
      // 汤温不带或无合格渗透单：后端同一改态口用中文拦下。
      setErr(ex.message);
    }
  }

  return (
    <div class="yard">
      <TopNav route={route} me={me} onLogout={onLogout} />
      <div class="heading">
        <h1>{board.filature}</h1>
        <p>
          {board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃
          <strong>且</strong>持有未作废、真空度 ≥ 0.08 的
          <a href="#/tickets">渗透合格单</a>
        </p>
      </div>
      <div class="ring">
        {board.basins.map((b, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const left = 50 + Math.cos(angle) * 38;
          const top = 50 + Math.sin(angle) * 38;
          return (
            <button
              key={b.id}
              class={`basin ${b.status}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              onClick={() => setPicked(b)}
            >
              <strong>{b.code}</strong>
              <span>{STATUS_LABEL[b.status]}</span>
              {b.hasQualifyingTicket && <span class="ticket-dot">渗</span>}
            </button>
          );
        })}
      </div>
      {picked && (
        <div class="drawer">
          <h3>
            {picked.code} · {STATUS_LABEL[picked.status]}
          </h3>
          <p>最近汤温：{picked.latestTempC ?? "无"} ℃ · 记录 {picked.readingCount} 次</p>
          <p>
            合格渗透单：
            {picked.hasQualifyingTicket ? (
              <span class="ok">单号 {picked.ticketSlipNo}（有效）</span>
            ) : (
              <span class="warn">无有效单，不能标已缫完</span>
            )}
          </p>
          <input value={temp} onInput={(e) => setTemp(e.target.value)} />
          <button onClick={writeTemp}>登记汤温</button>
          <div>
            <button onClick={() => setStatus("soaking")}>浸茧</button>
            <button onClick={() => setStatus("reeling")}>缫丝中</button>
            <button onClick={() => setStatus("reeled")}>已缫完</button>
          </div>
          {err && <p class="err">{err}</p>}
        </div>
      )}
    </div>
  );
}

function TicketsPage({ me, onLogout }) {
  const route = useRoute();
  const [board, setBoard] = useState(null);
  const [tickets, setTickets] = useState([]);
  const [allTickets, setAllTickets] = useState([]);
  const [filterBasin, setFilterBasin] = useState("");
  const [form, setForm] = useState({
    basinId: "",
    slipNo: "",
    vacuum: "",
    penetratedAt: "",
  });
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  async function loadBoard() {
    const data = await api("/api/board");
    setBoard(data);
    setForm((f) => ({ ...f, basinId: f.basinId || String(data.basins[0]?.id || "") }));
  }

  async function loadTickets() {
    const qs = filterBasin ? `?basin_id=${encodeURIComponent(filterBasin)}` : "";
    const data = await api(`/api/tickets${qs}`);
    setTickets(data.tickets);
  }

  async function loadAllAndSuggest() {
    // 单号建议须基于全量（与表格的按盆筛选互不影响）。
    const data = await api("/api/tickets");
    setAllTickets(data.tickets);
    setForm((f) => {
      if (!f.basinId) return f;
      const maxNo = data.tickets
        .filter((t) => String(t.basinId) === String(f.basinId))
        .reduce((m, t) => Math.max(m, t.slipNo), 0);
      return { ...f, slipNo: f.slipNo === "" ? String(maxNo + 1) : f.slipNo };
    });
  }

  useEffect(() => {
    (async () => {
      try {
        await loadBoard();
        await loadAllAndSuggest();
        await loadTickets();
      } catch (e) {
        setErr(e.message);
      }
    })();
  }, []);
  useEffect(() => {
    loadTickets().catch((e) => setErr(e.message));
  }, [filterBasin]);

  // 选定盆时，建议单号 = 该盆历史最大号 + 1（作废号也不回收），可手改。
  function suggestSlip(basinId) {
    const maxNo = allTickets
      .filter((t) => String(t.basinId) === String(basinId))
      .reduce((m, t) => Math.max(m, t.slipNo), 0);
    return maxNo + 1;
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setMsg("");
    const payload = {
      basinId: Number(form.basinId),
      slipNo: Number(form.slipNo),
      vacuum: Number(form.vacuum),
    };
    if (form.penetratedAt) {
      payload.penetratedAt = new Date(form.penetratedAt).toISOString();
    }
    try {
      await api("/api/tickets", { method: "POST", body: JSON.stringify(payload) });
      setMsg("渗透单已建");
      setForm((f) => ({ ...f, slipNo: "", vacuum: "", penetratedAt: "" }));
      await loadAllAndSuggest();
      await loadTickets();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidTicket(id) {
    setErr("");
    setMsg("");
    try {
      await api(`/api/tickets/${id}/void`, { method: "POST" });
      setMsg("该单已作废");
      await loadTickets();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  const basinName = (id) => board?.basins.find((b) => b.id === id)?.code || id;

  return (
    <div class="yard tickets-page">
      <TopNav route={route} me={me} onLogout={onLogout} />
      <div class="heading">
        <h1>渗透合格单</h1>
        <p>真空度须 ≥ 0.08；单仅作已缫完放行依据之一，汤温不达标仍不能出带。</p>
      </div>

      <form class="ticket-form" onSubmit={submit}>
        <label>
          盆
          <select
            value={form.basinId}
            onChange={(e) =>
              setForm((f) => ({
                ...f,
                basinId: e.target.value,
                slipNo: suggestSlip(e.target.value),
              }))
            }
          >
            {(board?.basins || []).map((b) => (
              <option value={b.id}>{b.code}</option>
            ))}
          </select>
        </label>
        <label>
          单号（该盆从 1 起）
          <input
            type="number"
            min="1"
            step="1"
            required
            value={form.slipNo}
            onInput={(e) => setForm((f) => ({ ...f, slipNo: e.target.value }))}
          />
        </label>
        <label>
          真空度（MPa）
          <input
            type="number"
            min="0"
            step="0.01"
            required
            placeholder="如 0.08"
            value={form.vacuum}
            onInput={(e) => setForm((f) => ({ ...f, vacuum: e.target.value }))}
          />
        </label>
        <label>
          渗透时刻（留空为现在）
          <input
            type="datetime-local"
            value={form.penetratedAt}
            onInput={(e) => setForm((f) => ({ ...f, penetratedAt: e.target.value }))}
          />
        </label>
        <button type="submit">建单</button>
      </form>

      <div class="ticket-filter">
        <label>
          按盆筛选：
          <select value={filterBasin} onChange={(e) => setFilterBasin(e.target.value)}>
            <option value="">全部盆</option>
            {(board?.basins || []).map((b) => (
              <option value={b.id}>{b.code}</option>
            ))}
          </select>
        </label>
      </div>

      {err && <p class="err">{err}</p>}
      {msg && <p class="ok">{msg}</p>}

      <table class="ticket-table">
        <thead>
          <tr>
            <th>盆</th>
            <th>单号</th>
            <th>真空度</th>
            <th>渗透时刻</th>
            <th>操作人</th>
            <th>状态</th>
            <th>作废时刻</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {tickets.length === 0 && (
            <tr>
              <td colspan="8" class="empty">
                暂无渗透单
              </td>
            </tr>
          )}
          {tickets.map((t) => (
            <tr key={t.id} class={t.voidedAt ? "voided" : ""}>
              <td>{basinName(t.basinId)}</td>
              <td>{t.slipNo}</td>
              <td class={t.vacuum >= 0.08 ? "ok" : "warn"}>{t.vacuum}</td>
              <td>{fmtTime(t.penetratedAt)}</td>
              <td>{t.operator}</td>
              <td>{t.voidedAt ? "已作废" : t.valid ? "有效" : "真空度不足"}</td>
              <td>{fmtTime(t.voidedAt)}</td>
              <td>
                {me?.role === "admin" && !t.voidedAt && (
                  <button class="void-btn" onClick={() => voidTicket(t.id)}>
                    作废
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function App() {
  const [ready, setReady] = useState(Boolean(token()));
  const [me, setMe] = useState(null);
  const route = useRoute();

  async function loadMe() {
    if (!token()) {
      setMe(null);
      return;
    }
    try {
      setMe(await api("/api/auth/me"));
    } catch {
      clearToken();
      setReady(false);
      setMe(null);
    }
  }

  useEffect(() => {
    if (ready) loadMe();
  }, [ready]);

  if (!ready) {
    return <Login onOk={() => setReady(true)} />;
  }

  const onLogout = () => {
    clearToken();
    setMe(null);
    setReady(false);
  };

  if (route.startsWith("#/tickets")) {
    return <TicketsPage me={me} onLogout={onLogout} />;
  }
  return <Yard me={me} onLogout={onLogout} />;
}

render(<App />, document.getElementById("app"));
