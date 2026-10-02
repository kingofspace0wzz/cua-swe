import json,sys
from support_geometry import solve
q=json.load(sys.stdin)
json.dump(solve(q['o'],q['d'],q['support']),sys.stdout)
