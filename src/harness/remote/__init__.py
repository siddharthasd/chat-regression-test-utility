"""Shared infrastructure for the harness's remote-HTTP-service clients.

Connector (007) and evaluator (008) both talk to remote services over the same
four auth modes; the auth-header construction and just-in-time credential
decryption live here once (extracted during the 007+008 foundation rollup).
"""
