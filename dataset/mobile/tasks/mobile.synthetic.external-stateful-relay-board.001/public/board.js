// Board integration. Ports use the simulator's local a/b and D/EN vocabulary.
export const board = {
  gates: [
    {id:'A1',type:'OR',a:'Tap',b:'Q0'},
    {id:'A2',type:'XOR',a:'Sweep',b:'Q2'},
    {id:'A3',type:'MASK',a:'A2',b:'A1'},
    {id:'B1',type:'XOR',a:'A2',b:'Q1'},
    {id:'B2',type:'AND',a:'A3',b:'E0'},
    {id:'B3',type:'OR',a:'B1',b:'B2'},
    {id:'C1',type:'XOR',a:'B3',b:'Q0'},
    {id:'C2',type:'OR',a:'Q1',b:'Q2'}
  ],
  memories: [
    {id:'Q0',D:'A3',EN:'E0'},
    {id:'Q1',D:'B3',EN:'E1'},
    {id:'Q2',D:'C1',EN:'E0'}
  ],
  lights: [{id:'Flare',from:'C1'},{id:'Wash',from:'C2'},{id:'Pearl',from:'Q2'}]
};
