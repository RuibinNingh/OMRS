/* 可信后端模板配置；不读取上游脚本，不动态加载TeX扩展。 */
window.MathJax = {
  loader: { load: ['ui/safe'] },
  startup: { typeset: false },
  tex: {
    inlineMath: [['$', '$'], ['\\(', '\\)']],
    displayMath: [['$$', '$$'], ['\\[', '\\]']],
    processEscapes: true,
    packages: ['base', 'ams', 'newcommand', 'configmacros', 'mhchem', 'cancel', 'color',
      'bbox', 'boldsymbol', 'enclose', 'extpfeil', 'mathtools', 'unicode', 'textmacros'],
    formatError: (_jax, error) => { throw error; },
  },
  chtml: { fontURL: 'https://omrs-render.invalid/vendor/mathjax/output/chtml/fonts/woff-v2' },
  options: {
    enableMenu: false,
    safeOptions: { allow: { URLs: 'none', classes: 'none', cssIDs: 'none', styles: 'none' } },
    compileError: (_document, _math, error) => { throw error; },
    typesetError: (_document, _math, error) => { throw error; },
  },
};
