import React from "react";
import { Link, NavLink } from "react-router-dom";

export default function Navbar({ auth }) {
  return (
    <header className="navbar">
      <Link className="brand" to="/">
        <span className="brand-badge" />
        Rental Listings
      </Link>

      <nav className="navlinks">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          Home
        </NavLink>

        {/* Protected navigation is disabled until the session is confirmed */}
        {auth.loggedIn ? (
          <>
            <NavLink to="/create" className={({ isActive }) => (isActive ? "active" : "")}>
              Add Listing
            </NavLink>
            <NavLink to="/update" className={({ isActive }) => (isActive ? "active" : "")}>
              Update Listing
            </NavLink>
          </>
        ) : (
          <>
            <a className="disabled-link" aria-disabled="true" title="Login required">
              Add Listing
            </a>
            <a className="disabled-link" aria-disabled="true" title="Login required">
              Update Listing
            </a>
          </>
        )}
      </nav>
    </header>
  );
}
