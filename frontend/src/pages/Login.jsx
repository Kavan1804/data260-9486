import React, { useState } from "react";
import { errorMessage, login, logout } from "../api/listingsApi.js";

export default function Login({ auth, setAuth }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const user = await login(email.trim(), password);
      setAuth({ checked: true, loggedIn: true, user });
      setPassword("");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } finally {
      setAuth({ checked: true, loggedIn: false, user: null });
    }
  }

  if (auth.loggedIn) {
    return (
      <div className="loginbar">
        <div className="loginbar-text">
          Logged in as <b>{auth.user.name}</b> ({auth.user.email})
        </div>
        <button className="btn danger" onClick={handleLogout}>
          Logout
        </button>
      </div>
    );
  }

  return (
    <div className="loginbar">
      <form className="loginbar-form" onSubmit={handleLogin}>
        <div className="loginbar-text">Not logged in</div>
        <input
          className="loginbar-input"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          className="loginbar-input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button className="btn primary" type="submit">
          Login
        </button>
        {error && <div className="error-text">{error}</div>}
      </form>
    </div>
  );
}
