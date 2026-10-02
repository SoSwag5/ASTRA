/** Novice setup gates, legacy progress and optional imports, with fictional facts. */
const assert = require('node:assert/strict');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
(async () => {
  const {createServer} = await import('vite');
  const server = await createServer({configFile:false,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true},appType:'custom',logLevel:'error'});
  try {
    const S = await server.ssrLoadModule('/src/SetupWizard.tsx');
    assert.equal(S.setupStep(8),5);
    assert.equal(S.setupStep(0),1);
    assert.equal(S.mayContinue(1,null,{}),false);
    assert.equal(S.mayContinue(2,{confirmed:false},{}),false);
    assert.equal(S.mayContinue(3,null,{}),true);
    assert.equal(S.mayContinue(4,{confirmed:true},{search_focus_confirmed:false}),false);
    assert.equal(S.mayContinue(4,{confirmed:true},{search_focus_confirmed:true}),true);
    const noop = () => {}, asyncNoop = async () => {};
    const props = {profile:{name:'Fictional Graduate',summary:'Fictional summary',skills:[{text:'Excel'}]},cfg:{provider:'rules'},api:asyncNoop,reload:asyncNoop,upload:asyncNoop,confirmProfile:asyncNoop,editProfile:noop,close:noop,back:noop,next:asyncNoop};
    const html = step => renderToStaticMarkup(React.createElement(S.SetupWizard,{...props,step}));
    assert.match(html(2),/Fictional summary/);
    assert.match(html(2),/Excel/);
    assert.match(html(3),/Skip for now/);
    assert.match(html(3),/optional/i);
    assert.match(html(5),/Rule-based matching is the recommended/);
    assert.match(html(5),/Confirm and start scan/);
    assert.doesNotMatch(html(5),/<select/);
    console.log('14 novice setup, review, optional-tracker and rule-based checks passed.');
  } finally {await server.close();}
})().catch(e => {console.error(e);process.exit(1);});
