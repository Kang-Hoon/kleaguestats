const fs=require('fs'); const R=require('../records.js');
const rd=n=>R.parseCSV(fs.readFileSync(__dirname+'/../data/sample/'+n+'.csv','utf8'));
const model=R.buildModel({matches:rd('matches'),roster:rd('roster'),events:rd('events')});
const q=R.query(model,{}); const out={issues:model.issues.map(i=>i.code),lists:{}};
q.lists.forEach(l=>out.lists[l.id]=l.rows.map(r=>[r.rank,r.name,r.value]));
console.log(JSON.stringify(out));
