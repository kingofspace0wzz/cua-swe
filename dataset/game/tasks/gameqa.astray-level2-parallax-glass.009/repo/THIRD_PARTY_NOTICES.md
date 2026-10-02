# Third-party notices

The snapshot preserves the original source headers in each vendored file.

| Component | Included file | Notice visible in discovery source | Publication action |
| --- | --- | --- | --- |
| Astray by Rye Terrell | `index.html`, `maze.js`, original documentation | GameWorld `RIGHTS.md` identifies Unlicense; original README states unrestricted intent | Retain `README.md`, `RIGHTS.md`, attribution, source URL, and obtain/retain the complete upstream license text before promotion |
| Three.js revision 49 | `Three.js` | Header identifies the Three.js project and source repository | Verify the exact revision's upstream license and add its complete notice before promotion |
| Box2dWeb | `Box2dWeb.min.js` | No complete notice is embedded in the minified discovery file | Resolve exact upstream revision and license before promotion |
| jQuery 1.7.2 | `jquery.js` | Header identifies jQuery 1.7.2 and its license URL | Preserve header and add the applicable full upstream notice before promotion |
| KeyboardJS | `keyboard.js` | Header states BSD License and identifies Robert William Hurst | Preserve header and add the complete BSD notice before promotion |

The candidate is quarantined and not part of a published dataset. Browser
certification and dataset promotion must remain blocked until the incomplete
third-party notices—especially Box2dWeb and the exact Three.js revision—have
been resolved.

