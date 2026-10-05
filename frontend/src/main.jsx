import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { api, clearToken, savedUser, saveUser, setToken, token } from "./api.js";
import "./app.css";

const STATUS_LABEL = { soaking: "浸茧", reeling: "缫丝中", reeled: "已缫完" };

function useHashRoute() {
  const [hash, setHash] = useState(location.hash || "#/yard");
  useEffect(() => {
    const onChange = () => setHash(location.hash || "#/yard");
    addEventListener("hashchange", onChange);
    return () => removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

function fmt(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false });
}

function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
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
      saveUser(data.user);
      onOk(data.user);
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
          <input name="username" autocomplete="off" value={username} onInput={(e) => setUsername(e.target.value)} />
        </label>
        <label>
          密码
          <input name="password" type="password" autocomplete="off" value={password} onInput={(e) => setPassword(e.target.value)} />
        </label>
        <p class="hint">已预填 admin / 123456，另有 worker / 123456</p>
        <button type="submit">登录</button>
      </form>
      {err && <p class="err">{err}</p>}
    </div>
  );
}

function Yard() {
  const [board, setBoard] = useState(null);
  const [picked, setPicked] = useState(null);
  const [temp, setTemp] = useState("40");
  const [err, setErr] = useState("");

  async function refresh() {
    const data = await api("/api/board");
    setBoard(data);
    if (picked) {
      setPicked(data.basins.find((b) => b.id === picked.id) || data.basins[0]);
    }
  }

  useEffect(() => {
    refresh().catch((e) => setErr(e.message));
  }, []);

  if (!board) {
    return (
      <div>
        {err || "装载环盆…"}
      </div>
    );
  }

  const n = board.basins.length;
  async function writeTemp() {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/readings`, {
        method: "POST",
        body: JSON.stringify({ waterTempC: Number(temp) }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }
  async function setStatus(status) {
    setErr("");
    try {
      const row = await api(`/api/basins/${picked.id}/status`, {
        method: "POST",
        body: JSON.stringify({ status }),
      });
      await refresh();
      setPicked(row);
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div>
      <p class="sub">
        {board.filature} · {board.riverside} · 点盆登记汤温；已缫完须最近汤温 38～42℃ 且有合格渗透单
      </p>
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
            合格渗透单：{picked.hasQualifiedSlip ? "有" : "无"} · 未作废单 {picked.liveSlipCount} 张
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

function Slips({ user }) {
  const [basins, setBasins] = useState([]);
  const [slips, setSlips] = useState([]);
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({ basinId: "", slipNo: "1", vacuum: "0.08", penetratedAt: nowLocal() });
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const isAdmin = user.role === "admin";

  async function loadSlips(basinId = filter) {
    const q = basinId ? `?basin_id=${basinId}` : "";
    const data = await api(`/api/slips${q}`);
    setSlips(data.slips);
  }

  useEffect(() => {
    api("/api/board")
      .then((d) => {
        setBasins(d.basins);
        if (d.basins.length) {
          setForm((f) => (f.basinId ? f : { ...f, basinId: String(d.basins[0].id) }));
        }
      })
      .catch((e) => setErr(e.message));
    loadSlips("").catch((e) => setErr(e.message));
  }, []);

  // 选定盆后建议下一个单号：该盆现有最大单号 + 1
  useEffect(() => {
    if (!form.basinId) return;
    api(`/api/slips?basin_id=${form.basinId}`)
      .then((d) => {
        const max = d.slips.reduce((m, s) => Math.max(m, s.slipNo), 0);
        setForm((f) => ({ ...f, slipNo: String(max + 1) }));
      })
      .catch(() => {});
  }, [form.basinId]);

  function onFilter(e) {
    const v = e.target.value;
    setFilter(v);
    setErr("");
    loadSlips(v).catch((ex) => setErr(ex.message));
  }

  async function createSlip(e) {
    e.preventDefault();
    setErr("");
    setOk("");
    try {
      const body = {
        basinId: Number(form.basinId),
        slipNo: Number(form.slipNo),
        vacuumDegree: Number(form.vacuum),
      };
      if (form.penetratedAt) body.penetratedAt = new Date(form.penetratedAt).toISOString();
      const slip = await api("/api/slips", { method: "POST", body: JSON.stringify(body) });
      setOk(`已入库：${slip.basinCode} ${slip.slipNo} 号单`);
      if (filter && filter !== String(slip.basinId)) {
        setFilter(String(slip.basinId));
        await loadSlips(String(slip.basinId));
      } else {
        await loadSlips();
      }
      setForm((f) => ({ ...f, slipNo: String(Number(f.slipNo) + 1) }));
    } catch (ex) {
      setErr(ex.message);
    }
  }

  async function voidSlip(slip) {
    setErr("");
    setOk("");
    try {
      await api(`/api/slips/${slip.id}/void`, { method: "POST" });
      setOk(`已作废：${slip.basinCode} ${slip.slipNo} 号单`);
      await loadSlips();
    } catch (ex) {
      setErr(ex.message);
    }
  }

  return (
    <div class="slippage">
      <p class="sub">渗透合格单专页：未作废且真空度≥0.08 的单才作放行依据；建单人人可录，作废仅管理员。</p>

      <form class="slipform" onSubmit={createSlip}>
        <h3>新建渗透单</h3>
        <label>
          盆
          <select value={form.basinId} onInput={(e) => setForm({ ...form, basinId: e.target.value })}>
            {basins.map((b) => (
              <option key={b.id} value={b.id}>{b.code}</option>
            ))}
          </select>
        </label>
        <label>
          单号
          <input
            type="number"
            min="1"
            step="1"
            value={form.slipNo}
            onInput={(e) => setForm({ ...form, slipNo: e.target.value })}
          />
        </label>
        <label>
          真空度
          <input
            type="number"
            min="0"
            max="1"
            step="0.001"
            value={form.vacuum}
            onInput={(e) => setForm({ ...form, vacuum: e.target.value })}
          />
        </label>
        <label>
          渗透时刻
          <input
            type="datetime-local"
            value={form.penetratedAt}
            onInput={(e) => setForm({ ...form, penetratedAt: e.target.value })}
          />
        </label>
        <button type="submit">建单入库</button>
      </form>

      <div class="filterbar">
        按盆筛选：
        <select value={filter} onInput={onFilter}>
          <option value="">全部</option>
          {basins.map((b) => (
            <option key={b.id} value={b.id}>{b.code}</option>
          ))}
        </select>
      </div>

      {err && <p class="err">{err}</p>}
      {ok && <p class="ok">{ok}</p>}

      <table class="slips">
        <thead>
          <tr>
            <th>盆</th>
            <th>单号</th>
            <th>真空度</th>
            <th>渗透时刻</th>
            <th>操作人</th>
            <th>状态</th>
            <th>放行依据</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {slips.map((s) => (
            <tr key={s.id} class={s.voidedAt ? "voided" : ""}>
              <td>{s.basinCode}</td>
              <td>{s.slipNo}</td>
              <td>{s.vacuumDegree}</td>
              <td>{fmt(s.penetratedAt)}</td>
              <td>{s.operator}</td>
              <td>{s.voidedAt ? `已作废 ${fmt(s.voidedAt)}` : "有效"}</td>
              <td>
                {s.qualified ? (
                  <span class="badge yes">合格</span>
                ) : (
                  <span class="badge no">{s.voidedAt ? "不作数" : "真空度不足"}</span>
                )}
              </td>
              <td>{isAdmin && !s.voidedAt && <button onClick={() => voidSlip(s)}>作废</button>}</td>
            </tr>
          ))}
          {!slips.length && (
            <tr>
              <td colspan="8" class="hint">暂无渗透单</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function Shell({ user, onLogout }) {
  const route = useHashRoute();
  const onSlips = route.startsWith("#/slips");
  return (
    <div class="yard">
      <div class="topbar">
        <div>
          <h1>江口缫丝坞</h1>
          <nav class="tabs">
            <a href="#/yard" class={onSlips ? "" : "active"}>环盆作业台</a>
            <a href="#/slips" class={onSlips ? "active" : ""}>渗透单</a>
          </nav>
        </div>
        <div class="side">
          <span class="who">{user.username} · {user.role === "admin" ? "管理员" : "缫丝工"}</span>
          <button onClick={onLogout}>退出</button>
        </div>
      </div>
      {onSlips ? <Slips user={user} /> : <Yard />}
    </div>
  );
}

function App() {
  const [user, setUser] = useState(savedUser());
  const [checked, setChecked] = useState(Boolean(savedUser()) || !token());

  useEffect(() => {
    if (user || !token()) return;
    api("/api/auth/me")
      .then((u) => {
        saveUser(u);
        setUser(u);
      })
      .catch(() => clearToken())
      .finally(() => setChecked(true));
  }, []);

  if (!checked) {
    return <div class="yard">装载…</div>;
  }
  if (!user) {
    return <Login onOk={(u) => setUser(u)} />;
  }
  return (
    <Shell
      user={user}
      onLogout={() => {
        clearToken();
        setUser(null);
      }}
    />
  );
}

render(<App />, document.getElementById("app"));
