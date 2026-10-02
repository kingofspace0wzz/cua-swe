#!/usr/bin/env python3
from argparse import ArgumentParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

parser = ArgumentParser()
parser.add_argument('--port', required=True, type=int)
args = parser.parse_args()
ThreadingHTTPServer(('127.0.0.1', args.port), SimpleHTTPRequestHandler).serve_forever()
