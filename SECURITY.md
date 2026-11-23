# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories
("Report a vulnerability" on the Security tab) or by opening a private issue. Do
not open public issues for undisclosed vulnerabilities.

## Lab / intentionally vulnerable backend

The bundled backend (`backend/`) is the **SASE SUMMIT "Vulnerable Edition"** and
contains deliberate backdoors (SQL injection, command injection, path traversal,
`eval` RCE, auth bypass). It is for isolated lab use only and must never be
exposed to an untrusted network.

## Supported versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |
