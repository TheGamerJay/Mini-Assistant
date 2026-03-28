/**
 * CreationRecordInfo
 *
 * Public info page explaining what a Creation Record is,
 * what it does, and — critically — what it does NOT do.
 *
 * Route: /creation-record-info (page key: 'creation-record-info')
 * Accessible from the footer of every legal page.
 */

import React from 'react';
import LegalLayout from '../legal/LegalLayout';

export default function CreationRecordInfo() {
  return (
    <LegalLayout title="Creation Record" lastUpdated={null}>

      {/* ── Section 1 ─────────────────────────────────────────────── */}
      <h2>What is a Creation Record?</h2>
      <p>
        A Creation Record is a structured history of your project, including timestamps, versions,
        and activity logs.
      </p>
      <p>
        When you build or iterate on a project in Mini Assistant, activity is automatically logged —
        giving you a documented timeline you can export at any time.
      </p>

      {/* ── Section 2 ─────────────────────────────────────────────── */}
      <h2>What information is stored?</h2>
      <ul>
        <li>Project creation date</li>
        <li>Update history</li>
        <li>Version history</li>
        <li>Prompts and inputs (if applicable)</li>
        <li>Generated files</li>
        <li>Export history</li>
        <li>Publish history</li>
        <li>File hashes (where implemented)</li>
      </ul>

      {/* ── Section 3 ─────────────────────────────────────────────── */}
      <h2>How this helps you</h2>
      <ul>
        <li>Provides a clear timeline of your work</li>
        <li>Helps demonstrate authorship history</li>
        <li>Supports disputes or content claims</li>
        <li>Creates a verifiable project record you control</li>
      </ul>

      {/* ── Section 4 — MANDATORY, exact meaning preserved ──────────── */}
      <h2>Important limitations</h2>
      <p>
        The Creation Record is a <strong>documentation tool only</strong>.
      </p>
      <p>It does <strong>not</strong>:</p>
      <ul>
        <li>Guarantee legal ownership</li>
        <li>Replace copyright registration</li>
        <li>Act as legal proof on its own</li>
      </ul>
      <p>
        If you need formal protection for your work, please consult a qualified legal professional
        or register your copyright through the appropriate authority in your country.
      </p>

      {/* ── Section 5 — Best practices ───────────────────────────────── */}
      <h2>Best practices</h2>
      <ul>
        <li>Export your record regularly as your project evolves</li>
        <li>Keep backups of exported records in a safe location</li>
        <li>Use alongside formal legal protections where necessary</li>
      </ul>

    </LegalLayout>
  );
}
