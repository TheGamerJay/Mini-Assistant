import React, { useEffect, useMemo, useState } from "react";

// Set this if API is on another origin (e.g., Vite env var)
const API_BASE =
  (typeof window !== "undefined" && window.API_BASE) ||
  (typeof import !== "undefined" && typeof import.meta !== "undefined" && import.meta.env && (import.meta.env.VITE_API_BASE || import.meta.env.MCW_API_BASE)) ||
  "";

function Card({ title, children, footer }) {
  return (
    <div className="rounded-2xl shadow-lg p-4 bg-white/90 dark:bg-zinc-900/90 border border-zinc-200 dark:border-zinc-800 w-full">
      <div className="text-xl font-semibold mb-3">{title}</div>
      <div>{children}</div>
      {footer ? <div className="mt-4 pt-3 border-t border-zinc-200 dark:border-zinc-800">{footer}</div> : null}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm font-medium text-zinc-700 dark:text-zinc-200">{label}</span>
      {children}
    </label>
  );
}

function Button({ children, onClick, disabled, type="button" }) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="px-4 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 hover:bg-zinc-200 hover:dark:bg-zinc-700 transition disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function JsonBox({ data }) {
  return (
    <pre className="text-xs bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl p-3 overflow-auto max-h-48 whitespace-pre-wrap break-words">
      {data ? JSON.stringify(data, null, 2) : "—"}
    </pre>
  );
}

export default function MiniCasinoUI() {
  const [token, setToken] = useState(() => localStorage.getItem("mcw_token") || "");
  const [me, setMe] = useState(null);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("games");

  // Auth forms
  const [regUsername, setRegUsername] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [idIdentifier, setIdIdentifier] = useState("");
  const [idPassword, setIdPassword] = useState("");

  // Wallet
  const [depositAmt, setDepositAmt] = useState(25);

  // Games
  const [bjBet, setBjBet] = useState(10);
  const [rlBet, setRlBet] = useState(5);
  const [rlColor, setRlColor] = useState("red");
  const [slBet, setSlBet] = useState(1);

  const [bjRes, setBjRes] = useState(null);
  const [rlRes, setRlRes] = useState(null);
  const [slRes, setSlRes] = useState(null);

  // Store
  const [products, setProducts] = useState([]);
  const [storeRes, setStoreRes] = useState(null);

  // Community
  const [top, setTop] = useState([]);

  // Profile
  const [newUsername, setNewUsername] = useState("");
  const [betHistory, setBetHistory] = useState([]);
  const [txHistory, setTxHistory] = useState([]);

  const authHeaders = useMemo(() => (token ? { Authorization: `Bearer ${token}` } : {}), [token]);

  const api = useMemo(() => {
    const base = API_BASE.replace(/\/$/, "");
    return {
      register: (username, email, password) =>
        fetch(`${base}/api/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, email, password }),
          credentials: "include"
        }).then(r => r.json()),
      login: (identifier, password) =>
        fetch(`${base}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ identifier, password }),
          credentials: "include"
        }).then(r => r.json()),
      me: () =>
        fetch(`${base}/api/users/me`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      updateMe: (username) =>
        fetch(`${base}/api/users/me`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({ username }),
          credentials: "include"
        }).then(r => r.json()),
      balance: () =>
        fetch(`${base}/api/users/me/balance`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      deposit: (amount) =>
        fetch(`${base}/api/wallet/deposit`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({ amount }),
          credentials: "include"
        }).then(r => r.json()),
      storeProducts: () =>
        fetch(`${base}/api/store/products`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      storeCheckout: (product_id) =>
        fetch(`${base}/api/store/checkout`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({ product_id }),
          credentials: "include"
        }).then(r => r.json()),
      leaderboard: (window = "all") =>
        fetch(`${base}/api/leaderboard?window=${window}`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      historyBets: (limit = 25, offset = 0) =>
        fetch(`${base}/api/history/bets?limit=${limit}&offset=${offset}`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      historyTransactions: (limit = 25, offset = 0) =>
        fetch(`${base}/api/history/transactions?limit=${limit}&offset=${offset}`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      getSettings: () =>
        fetch(`${base}/api/users/me/settings`, {
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      updateSettings: (settings) =>
        fetch(`${base}/api/users/me/settings`, {
          method: "PUT",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify(settings),
          credentials: "include"
        }).then(r => r.json()),
      claimBonus: () =>
        fetch(`${base}/api/bonus/daily`, {
          method: "POST",
          headers: { ...authHeaders },
          credentials: "include"
        }).then(r => r.json()),
      blackjack: (bet) =>
        fetch(`${base}/api/blackjack/play`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({ bet }),
          credentials: "include"
        }).then(r => r.json()),
      roulette: (bet, color) =>
        fetch(`${base}/api/roulette/bet`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({ bet, color }),
          credentials: "include"
        }).then(r => r.json()),
      slots: (bet) =>
        fetch(`${base}/api/slots/spin`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...authHeaders },
          body: JSON.stringify({ bet }),
          credentials: "include"
        }).then(r => r.json()),
    };
  }, [authHeaders]);

  function setAuth(token, user) {
    localStorage.setItem("mcw_token", token);
    setToken(token);
    setMe(user);
    setNewUsername(user?.username || "");
  }

  async function withLoad(fn) {
    setLoading(true); setErr("");
    try {
      await fn();
    } catch (e) {
      console.error(e);
      setErr("Network or server error.");
    } finally {
      setLoading(false);
    }
  }

  const doRegister = () => withLoad(async () => {
    const res = await api.register(regUsername, regEmail, regPassword);
    if (res.access_token) {
      setAuth(res.access_token, res.user);
      const b = await api.balance();
      if (b.balance !== undefined) setBalance(b.balance);
    } else {
      setErr(res.error || "Register failed");
    }
  });

  const doLogin = () => withLoad(async () => {
    const res = await api.login(idIdentifier, idPassword);
    if (res.access_token) {
      setAuth(res.access_token, res.user);
      const b = await api.balance();
      if (b.balance !== undefined) setBalance(b.balance);
    } else {
      setErr(res.error || "Login failed");
    }
  });

  const refreshBalance = () => withLoad(async () => {
    const b = await api.balance();
    if (b.balance !== undefined) setBalance(b.balance);
    else setErr(b.error || "Unable to fetch balance");
  });

  const doDeposit = () => withLoad(async () => {
    const res = await api.deposit(Number(depositAmt));
    if (res.ok) setBalance(res.balance);
    else setErr(res.error || "Deposit failed");
  });

  const fetchStore = () => withLoad(async () => {
    const res = await api.storeProducts();
    if (Array.isArray(res)) setProducts(res);
    else setErr(res.error || "Store fetch failed");
  });

  const buyProduct = (pid) => withLoad(async () => {
    const res = await api.storeCheckout(pid);
    if (res.ok) {
      setStoreRes(res);
      setBalance(res.balance);
    } else {
      setErr(res.error || "Purchase failed");
    }
  });

  const fetchLeaderboard = () => withLoad(async () => {
    const res = await api.leaderboard();
    if (Array.isArray(res)) setTop(res);
    else setErr(res.error || "Leaderboard fetch failed");
  });

  const fetchHistory = () => withLoad(async () => {
    const [bets, txs] = await Promise.all([
      api.historyBets(25, 0),
      api.historyTransactions(25, 0)
    ]);
    if (Array.isArray(bets)) setBetHistory(bets);
    if (Array.isArray(txs)) setTxHistory(txs);
  });

  const saveProfile = () => withLoad(async () => {
    const res = await api.updateMe(newUsername);
    if (res.user) {
      setMe(res.user);
    } else {
      setErr(res.error || "Profile update failed");
    }
  });

  const playBJ = () => withLoad(async () => {
    const res = await api.blackjack(Number(bjBet));
    setBjRes(res);
    if (res.balance !== undefined) setBalance(res.balance);
    if (res.error) setErr(res.error);
  });

  const betRoulette = () => withLoad(async () => {
    const res = await api.roulette(Number(rlBet), rlColor);
    setRlRes(res);
    if (res.balance !== undefined) setBalance(res.balance);
    if (res.error) setErr(res.error);
  });

  const spinSlots = () => withLoad(async () => {
    const res = await api.slots(Number(slBet));
    setSlRes(res);
    if (res.balance !== undefined) setBalance(res.balance);
    if (res.error) setErr(res.error);
  });

  useEffect(() => {
    if (token) {
      refreshBalance();
      api.me().then(res => {
        if (res.user) {
          setMe(res.user);
          setNewUsername(res.user.username);
        }
      });
    }
  }, [token]);

  useEffect(() => {
    if (token && tab === "store" && products.length === 0) fetchStore();
    if (token && tab === "community") fetchLeaderboard();
    if (token && tab === "profile" && betHistory.length === 0) fetchHistory();
  }, [token, tab]);

  return (
    <div className="min-h-screen w-full bg-gradient-to-b from-zinc-50 to-zinc-200 dark:from-zinc-950 dark:to-zinc-900 text-zinc-900 dark:text-zinc-100 p-6">
      <div className="max-w-6xl mx-auto grid gap-6">
        <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-black tracking-tight">Mini Casino World</h1>
            <p className="text-sm text-zinc-600 dark:text-zinc-400">Login • Wallet • Blackjack • Roulette • Slots</p>
          </div>
          <div className="flex items-end gap-6">
            <div className="flex flex-col">
              <div className="text-sm text-zinc-600 dark:text-zinc-400">Balance</div>
              <div className="text-2xl font-bold">{balance === null ? "—" : Number(balance).toFixed(2)}</div>
            </div>
            <Button onClick={refreshBalance} disabled={loading || !token}>Refresh</Button>
          </div>
        </header>

        {err && <div className="rounded-xl border border-red-300 bg-red-50 text-red-800 p-3">{err}</div>}

        {!token ? (
          <div className="grid md:grid-cols-2 gap-6">
            <Card title="Create Account">
              <div className="grid gap-3">
                <Field label="Username">
                  <input value={regUsername} onChange={e=>setRegUsername(e.target.value)}
                         className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                </Field>
                <Field label="Email">
                  <input value={regEmail} onChange={e=>setRegEmail(e.target.value)}
                         className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                </Field>
                <Field label="Password (min 6)">
                  <input type="password" value={regPassword} onChange={e=>setRegPassword(e.target.value)}
                         className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                </Field>
                <Button onClick={doRegister} disabled={loading}>Sign Up</Button>
              </div>
            </Card>

            <Card title="Sign In">
              <div className="grid gap-3">
                <Field label="Email or Username">
                  <input value={idIdentifier} onChange={e=>setIdIdentifier(e.target.value)}
                         className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                </Field>
                <Field label="Password">
                  <input type="password" value={idPassword} onChange={e=>setIdPassword(e.target.value)}
                         className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                </Field>
                <Button onClick={doLogin} disabled={loading}>Login</Button>
              </div>
            </Card>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <div className="text-sm">Logged in as <b>{me?.username}</b></div>
              <Button onClick={() => { localStorage.removeItem("mcw_token"); setToken(""); setMe(null); setBalance(null); setTab("games"); }}>
                Logout
              </Button>
            </div>

            {/* Tab Navigation */}
            <div className="flex gap-2 border-b border-zinc-300 dark:border-zinc-700">
              {["games", "wallet", "store", "community", "profile"].map(t => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
                    tab === t
                      ? "border-zinc-900 dark:border-zinc-100 text-zinc-900 dark:text-zinc-100"
                      : "border-transparent text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 hover:dark:text-zinc-100"
                  }`}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>

            {tab === "games" && (
              <div className="grid md:grid-cols-3 gap-6">
                <Card title="Blackjack — Classic 21 vs House">
                  <div className="flex flex-col gap-3">
                    <Field label="Bet (chips)">
                      <input type="number" min={1} value={bjBet} onChange={e=>setBjBet(e.target.value)}
                             className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                    </Field>
                    <Button onClick={playBJ} disabled={loading}>Play Blackjack</Button>
                    <JsonBox data={bjRes} />
                  </div>
                </Card>

                <Card title="Roulette — Red or Black?">
                  <div className="flex flex-col gap-3">
                    <div className="flex gap-3">
                      <Field label="Bet (chips)">
                        <input type="number" min={1} value={rlBet} onChange={e=>setRlBet(e.target.value)}
                               className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                      </Field>
                      <Field label="Color">
                        <select value={rlColor} onChange={e=>setRlColor(e.target.value)}
                                className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60">
                          <option value="red">Red</option>
                          <option value="black">Black</option>
                        </select>
                      </Field>
                    </div>
                    <Button onClick={betRoulette} disabled={loading}>Spin Wheel</Button>
                    <JsonBox data={rlRes} />
                  </div>
                </Card>

                <Card title="Slots — Spin to Win (Chips Only)">
                  <div className="flex flex-col gap-3">
                    <Field label="Bet (chips)">
                      <input type="number" min={1} value={slBet} onChange={e=>setSlBet(e.target.value)}
                             className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                    </Field>
                    <Button onClick={spinSlots} disabled={loading}>Spin</Button>
                    <JsonBox data={slRes} />
                  </div>
                </Card>
              </div>
            )}

            {tab === "wallet" && (
              <Card title="Wallet — Add Funds">
                <div className="flex items-end gap-3">
                  <Field label="Amount">
                    <input type="number" min={1} value={depositAmt} onChange={e=>setDepositAmt(e.target.value)}
                           className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                  </Field>
                  <Button onClick={doDeposit} disabled={loading}>Deposit</Button>
                </div>
              </Card>
            )}

            {tab === "store" && (
              <div className="grid md:grid-cols-3 gap-6">
                {products.map(p => (
                  <Card key={p.id} title={p.name}>
                    <div className="text-sm text-zinc-600 dark:text-zinc-400 mb-2">{p.subtitle}</div>
                    <div className="text-3xl font-extrabold mb-3">+{p.chips.toLocaleString()} chips</div>
                    <Button onClick={()=>buyProduct(p.id)} disabled={loading}>Buy</Button>
                  </Card>
                ))}
                {storeRes && <Card title="Last Purchase"><JsonBox data={storeRes} /></Card>}
              </div>
            )}

            {tab === "community" && (
              <Card title="Leaderboard — Top Net Winnings">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left border-b border-zinc-200 dark:border-zinc-800">
                        <th className="py-2">#</th>
                        <th className="py-2">User</th>
                        <th className="py-2">Net Winnings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top.map((row, i) => (
                        <tr key={row.user_id} className="border-b border-zinc-100 dark:border-zinc-800">
                          <td className="py-2">{i+1}</td>
                          <td className="py-2">{row.username}</td>
                          <td className="py-2">{Number(row.net_winnings).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="text-xs text-zinc-500 mt-3">No chat, leaderboard only.</div>
              </Card>
            )}

            {tab === "profile" && (
              <div className="grid md:grid-cols-2 gap-6">
                <Card title="Your Profile">
                  <div className="grid gap-3">
                    <div className="text-sm">User ID: <b>{me?.id}</b></div>
                    <div className="text-sm">Email: <b>{me?.email}</b></div>
                    <Field label="Username">
                      <input value={newUsername} onChange={e=>setNewUsername(e.target.value)} className="px-3 py-2 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/60 dark:bg-zinc-800/60" />
                    </Field>
                    <div className="flex gap-2">
                      <Button onClick={saveProfile} disabled={loading}>Save</Button>
                    </div>
                  </div>
                </Card>
                <Card title="Stats & History">
                  <div className="text-sm text-zinc-600 dark:text-zinc-400">Balance</div>
                  <div className="text-2xl font-bold mb-3">{balance === null ? "—" : Number(balance).toFixed(2)}</div>
                  <div className="text-sm font-semibold mb-1">Recent Bets</div>
                  <div className="overflow-x-auto mb-4">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left border-b border-zinc-200 dark:border-zinc-800">
                          <th className="py-1">When</th>
                          <th className="py-1">Game</th>
                          <th className="py-1">Bet</th>
                          <th className="py-1">Payout</th>
                          <th className="py-1">Outcome</th>
                        </tr>
                      </thead>
                      <tbody>
                        {betHistory.map((b)=> (
                          <tr key={b.id} className="border-b border-zinc-100 dark:border-zinc-800">
                            <td className="py-1">{new Date(b.created_at).toLocaleString()}</td>
                            <td className="py-1">{b.game_type}</td>
                            <td className="py-1">{Number(b.amount).toFixed(2)}</td>
                            <td className="py-1">{Number(b.payout).toFixed(2)}</td>
                            <td className="py-1">{b.outcome}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="text-sm font-semibold mb-1">Recent Transactions</div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-left border-b border-zinc-200 dark:border-zinc-800">
                          <th className="py-1">When</th>
                          <th className="py-1">Type</th>
                          <th className="py-1">Amount</th>
                          <th className="py-1">Ref</th>
                        </tr>
                      </thead>
                      <tbody>
                        {txHistory.map((t)=> (
                          <tr key={t.id} className="border-b border-zinc-100 dark:border-zinc-800">
                            <td className="py-1">{new Date(t.created_at).toLocaleString()}</td>
                            <td className="py-1">{t.type}</td>
                            <td className="py-1">{Number(t.amount).toFixed(2)}</td>
                            <td className="py-1">{t.ref_code || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
            )}
          </>
        )}

        <footer className="text-xs text-zinc-500 pt-2">API Base: {API_BASE || window.location.origin}</footer>
      </div>
    </div>
  );
}