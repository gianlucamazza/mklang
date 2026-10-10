/* Gradio PINNED_HF_HUB worker (gradio#12262): @gradio/lite@5.45.0 webworker plus huggingface-hub==0.35.0 rewrite. */
(function(){"use strict";var H=Object.defineProperty,U=(e,t,o)=>t in e?H(e,t,{enumerable:!0,configurable:!0,writable:!0,value:o}):e[t]=o,I=(e,t,o)=>U(e,typeof t!="symbol"?t+"":t,o);function q(e){return e&&e.__esModule&&Object.prototype.hasOwnProperty.call(e,"default")?e.default:e}function _(e){if(typeof e!="string")throw new TypeError("Path must be a string. Received "+JSON.stringify(e))}function R(e,t){for(var o="",i=0,s=-1,a=0,n,r=0;r<=e.length;++r){if(r<e.length)n=e.charCodeAt(r);else{if(n===47)break;n=47}if(n===47){if(!(s===r-1||a===1))if(s!==r-1&&a===2){if(o.length<2||i!==2||o.charCodeAt(o.length-1)!==46||o.charCodeAt(o.length-2)!==46){if(o.length>2){var l=o.lastIndexOf("/");if(l!==o.length-1){l===-1?(o="",i=0):(o=o.slice(0,l),i=o.length-1-o.lastIndexOf("/")),s=r,a=0;continue}}else if(o.length===2||o.length===1){o="",i=0,s=r,a=0;continue}}t&&(o.length>0?o+="/..":o="..",i=2)}else o.length>0?o+="/"+e.slice(s+1,r):o=e.slice(s+1,r),i=r-s-1;s=r,a=0}else n===46&&a!==-1?++a:a=-1}return o}function W(e,t){var o=t.dir||t.root,i=t.base||(t.name||"")+(t.ext||"");return o?o===t.root?o+i:o+e+i:i}var b={resolve:function(){for(var e="",t=!1,o,i=arguments.length-1;i>=-1&&!t;i--){var s;i>=0?s=arguments[i]:(o===void 0&&(o=process.cwd()),s=o),_(s),s.length!==0&&(e=s+"/"+e,t=s.charCodeAt(0)===47)}return e=R(e,!t),t?e.length>0?"/"+e:"/":e.length>0?e:"."},normalize:function(e){if(_(e),e.length===0)return".";var t=e.charCodeAt(0)===47,o=e.charCodeAt(e.length-1)===47;return e=R(e,!t),e.length===0&&!t&&(e="."),e.length>0&&o&&(e+="/"),t?"/"+e:e},isAbsolute:function(e){return _(e),e.length>0&&e.charCodeAt(0)===47},join:function(){if(arguments.length===0)return".";for(var e,t=0;t<arguments.length;++t){var o=arguments[t];_(o),o.length>0&&(e===void 0?e=o:e+="/"+o)}return e===void 0?".":b.normalize(e)},relative:function(e,t){if(_(e),_(t),e===t||(e=b.resolve(e),t=b.resolve(t),e===t))return"";for(var o=1;o<e.length&&e.charCodeAt(o)===47;++o);for(var i=e.length,s=i-o,a=1;a<t.length&&t.charCodeAt(a)===47;++a);for(var n=t.length,r=n-a,l=s<r?s:r,p=-1,c=0;c<=l;++c){if(c===l){if(r>l){if(t.charCodeAt(a+c)===47)return t.slice(a+c+1);if(c===0)return t.slice(a+c)}else s>l&&(e.charCodeAt(o+c)===47?p=c:c===0&&(p=0));break}var h=e.charCodeAt(o+c),u=t.charCodeAt(a+c);if(h!==u)break;h===47&&(p=c)}var f="";for(c=o+p+1;c<=i;++c)(c===i||e.charCodeAt(c)===47)&&(f.length===0?f+="..":f+="/..");return f.length>0?f+t.slice(a+p):(a+=p,t.charCodeAt(a)===47&&++a,t.slice(a))},_makeLong:function(e){return e},dirname:function(e){if(_(e),e.length===0)return".";for(var t=e.charCodeAt(0),o=t===47,i=-1,s=!0,a=e.length-1;a>=1;--a)if(t=e.charCodeAt(a),t===47){if(!s){i=a;break}}else s=!1;return i===-1?o?"/":".":o&&i===1?"//":e.slice(0,i)},basename:function(e,t){if(t!==void 0&&typeof t!="string")throw new TypeError('"ext" argument must be a string');_(e);var o=0,i=-1,s=!0,a;if(t!==void 0&&t.length>0&&t.length<=e.length){if(t.length===e.length&&t===e)return"";var n=t.length-1,r=-1;for(a=e.length-1;a>=0;--a){var l=e.charCodeAt(a);if(l===47){if(!s){o=a+1;break}}else r===-1&&(s=!1,r=a+1),n>=0&&(l===t.charCodeAt(n)?--n===-1&&(i=a):(n=-1,i=r))}return o===i?i=r:i===-1&&(i=e.length),e.slice(o,i)}else{for(a=e.length-1;a>=0;--a)if(e.charCodeAt(a)===47){if(!s){o=a+1;break}}else i===-1&&(s=!1,i=a+1);return i===-1?"":e.slice(o,i)}},extname:function(e){_(e);for(var t=-1,o=0,i=-1,s=!0,a=0,n=e.length-1;n>=0;--n){var r=e.charCodeAt(n);if(r===47){if(!s){o=n+1;break}continue}i===-1&&(s=!1,i=n+1),r===46?t===-1?t=n:a!==1&&(a=1):t!==-1&&(a=-1)}return t===-1||i===-1||a===0||a===1&&t===i-1&&t===o+1?"":e.slice(t,i)},format:function(e){if(e===null||typeof e!="object")throw new TypeError('The "pathObject" argument must be of type Object. Received type '+typeof e);return W("/",e)},parse:function(e){_(e);var t={root:"",dir:"",base:"",ext:"",name:""};if(e.length===0)return t;var o=e.charCodeAt(0),i=o===47,s;i?(t.root="/",s=1):s=0;for(var a=-1,n=0,r=-1,l=!0,p=e.length-1,c=0;p>=s;--p){if(o=e.charCodeAt(p),o===47){if(!l){n=p+1;break}continue}r===-1&&(l=!1,r=p+1),o===46?a===-1?a=p:c!==1&&(c=1):a!==-1&&(c=-1)}return a===-1||r===-1||c===0||c===1&&a===r-1&&a===n+1?r!==-1&&(n===0&&i?t.base=t.name=e.slice(1,r):t.base=t.name=e.slice(n,r)):(n===0&&i?(t.name=e.slice(1,a),t.base=e.slice(1,r)):(t.name=e.slice(n,a),t.base=e.slice(n,r)),t.ext=e.slice(a,r)),n>0?t.dir=e.slice(0,n-1):i&&(t.dir="/"),t},sep:"/",delimiter:":",win32:null,posix:null};b.posix=b;var G=b;const T=q(G),j="/home/pyodide",v=e=>`${j}/${e}`,w=(e,t)=>T.resolve(v(e),t);function L(e,t){const o=T.normalize(t),i=T.dirname(o).split("/"),s=[];for(const a of i){s.push(a);const n=s.join("/");if(e.FS.analyzePath(n).exists){if(e.FS.isDir(n))throw new Error(`"${n}" already exists and is not a directory.`);continue}try{e.FS.mkdir(n)}catch(r){throw console.error(`Failed to create a directory "${n}"`),r}}}function N(e,t,o,i){L(e,t),e.FS.writeFile(t,o,i)}function Y(e,t,o){L(e,o),e.FS.rename(t,o)}function z(e){e.forEach(t=>{let o;try{o=new URL(t)}catch{return}if(o.protocol==="emfs:"||o.protocol==="file:")throw new Error(`"emfs:" and "file:" protocols are not allowed for the requirement (${t})`)})}function B(e,t){const o=e.pyimport("packaging.requirements.Requirement");try{const i=o(t);return i.name==="plotly"&&i.specifier.contains("6")}catch{return!1}}function $(e,t){const o=e.pyimport("packaging.requirements.Requirement");try{return o(t).name==="altair"}catch{return!1}}function V(e,t){const o="huggingface-hub==0.35.0";function i(l){try{return new URL(l).pathname.split("/").pop()??null}catch{return null}}function s(l,p){const c=i(l);if(!c)return!1;const h=c.toLowerCase(),u=p.toLowerCase().replace(/_/g,"-"),f=p.toLowerCase().replace(/-/g,"_");return h.startsWith(`${u}-`)||h.startsWith(`${f}-`)}function a(l,p){try{return e.pyimport("packaging.requirements.Requirement")(l).name===p}catch{return s(l,p)}}let n=!1;const r=t.map(l=>a(l,"huggingface-hub")?(n=!0,o):l);return(r.some(l=>a(l,"gradio")||a(l,"gradio-client")||a(l,"gradio_client"))||n)&&!r.some(l=>l===o)&&r.push(o),r.some(l=>$(e,l))?r.map(l=>B(e,l)?"plotly==5.*":l):r}class J{constructor(){I(this,"_buffer",[]),I(this,"_promise"),I(this,"_resolve"),this._resolve=null,this._promise=null,this._notifyAll()}async _wait(){await this._promise}_notifyAll(){this._resolve&&this._resolve(),this._promise=new Promise(t=>this._resolve=t)}async dequeue(){for(;this._buffer.length===0;)await this._wait();return this._buffer.shift()}enqueue(t){this._buffer.push(t),this._notifyAll()}}function K(e,t,o){const i=new J;o.addEventListener("message",n=>{i.enqueue(n.data)}),o.start();async function s(){return await i.dequeue()}async function a(n){const r=Object.fromEntries(n.toJs());o.postMessage(r)}return e(t,s,a)}const P="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";function X(e){return Array.from(Array(e)).map(()=>P[Math.floor(Math.random()*P.length)]).join("")}const Q=`import jedi


def get_code_completions(code: str, line: int, column: int):
    script = jedi.Script(code)
    completions = script.complete(line, column)
    serializable_completions = [
        {
            "label": completion.name,
            "type": completion.type,
            "docstring": completion.docstring(raw=True),
            "completion_prefix_length": completion.get_completion_prefix_length(),
        }
        for completion in completions
    ]
    return serializable_completions
`;class Z{constructor(t){I(this,"setupPromise"),this.pyodide=t,this.setupPromise=this.setup().catch(o=>(console.error("Error while setting up code completion",o),null))}async setup(){return await this.pyodide.pyimport("micropip").install.callKwargs(["jedi"],{keep_going:!0}),this.pyodide.runPython(Q),this.pyodide.globals.get("get_code_completions")}async getCodeCompletions(t){const o=await this.setupPromise;if(!o)return console.debug("Code completion setup failed, returning empty response"),[];const{code:i,line:s,column:a}=t,n=o(i,s,a),r=n.toJs({dict_converter:Object.fromEntries});return n.destroy(),r}}const ee=`import ast
import os
import sys
import tokenize
import types
from inspect import CO_COROUTINE

from gradio.wasm_utils import app_id_context

# BSD 3-Clause License
#
# - Copyright (c) 2008-Present, IPython Development Team
# - Copyright (c) 2001-2007, Fernando Perez <fernando.perez@colorado.edu>
# - Copyright (c) 2001, Janko Hauser <jhauser@zscout.de>
# - Copyright (c) 2001, Nathaniel Gray <n8gray@caltech.edu>
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.

# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.

# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# Code modified from IPython (BSD license)
# Source: https://github.com/ipython/ipython/blob/master/IPython/utils/syspathcontext.py#L42
class modified_sys_path:  # noqa: N801
    """A context for prepending a directory to sys.path for a second."""

    def __init__(self, script_path: str):
        self._script_path = script_path
        self._added_path = False

    def __enter__(self):
        if self._script_path not in sys.path:
            sys.path.insert(0, self._script_path)
            self._added_path = True

    def __exit__(self, type, value, traceback):
        if self._added_path:
            try:
                sys.path.remove(self._script_path)
            except ValueError:
                # It's already removed.
                pass

        # Returning False causes any exceptions to be re-raised.
        return False


# Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022)
# Copyright (c) Yuichiro Tachibana (2023)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
def _new_module(name: str) -> types.ModuleType:
    """Create a new module with the given name."""
    return types.ModuleType(name)


def set_home_dir(home_dir: str) -> None:
    os.environ["HOME"] = home_dir
    os.chdir(home_dir)


async def _run_script(app_id: str, home_dir: str, script_path: str) -> None:
    # This function is based on the following code from Streamlit:
    # https://github.com/streamlit/streamlit/blob/1.24.0/lib/streamlit/runtime/scriptrunner/script_runner.py#L519-L554
    # with modifications to support top-level await.
    set_home_dir(home_dir)

    with tokenize.open(script_path) as f:
        filebody = f.read()

    await _run_code(app_id, home_dir, filebody, script_path)


async def _run_code(
        app_id: str,
        home_dir: str,
        filebody: str,
        script_path: str = '<string>'  # This default value follows the convention. Ref: https://docs.python.org/3/library/functions.html#compile
    ) -> None:
    set_home_dir(home_dir)

    # NOTE: In Streamlit, the bytecode caching mechanism has been introduced.
    # However, we skipped it here for simplicity and because Gradio doesn't need to rerun the script so frequently,
    # while we may do it in the future.
    bytecode = compile(  # type: ignore
        filebody,
        # Pass in the file path so it can show up in exceptions.
        script_path,
        # We're compiling entire blocks of Python, so we need "exec"
        # mode (as opposed to "eval" or "single").
        mode="exec",
        # Don't inherit any flags or "future" statements.
        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT, # Allow top-level await. Ref: https://github.com/whitphx/streamlit/commit/277dc580efb315a3e9296c9a0078c602a0904384
        dont_inherit=1,
        # Use the default optimization options.
        optimize=-1,
    )

    module = _new_module("__main__")

    # Install the fake module as the __main__ module. This allows
    # the pickle module to work inside the user's code, since it now
    # can know the module where the pickled objects stem from.
    # IMPORTANT: This means we can't use "if __name__ == '__main__'" in
    # our code, as it will point to the wrong module!!!
    sys.modules["__main__"] = module

    # Add special variables to the module's globals dict.
    module.__dict__["__file__"] = script_path

    with modified_sys_path(script_path), modified_sys_path(home_dir), app_id_context(app_id):
        # Allow top-level await. Ref: https://github.com/whitphx/streamlit/commit/277dc580efb315a3e9296c9a0078c602a0904384
        if bytecode.co_flags & CO_COROUTINE:
            # The source code includes top-level awaits, so the compiled code object is a coroutine.
            await eval(bytecode, module.__dict__)
        else:
            exec(bytecode, module.__dict__)
`,te=`# Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022)
# Copyright (c) Yuichiro Tachibana (2023)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import fnmatch
import logging
import os
import sys
import types
from typing import Optional, Set

LOGGER = logging.getLogger(__name__)

#
# Copied from https://github.com/streamlit/streamlit/blob/1.24.0/lib/streamlit/file_util.py
#

def file_is_in_folder_glob(filepath, folderpath_glob) -> bool:
    """Test whether a file is in some folder with globbing support.

    Parameters
    ----------
    filepath : str
        A file path.
    folderpath_glob: str
        A path to a folder that may include globbing.

    """
    # Make the glob always end with "/*" so we match files inside subfolders of
    # folderpath_glob.
    if not folderpath_glob.endswith("*"):
        if folderpath_glob.endswith("/"):
            folderpath_glob += "*"
        else:
            folderpath_glob += "/*"

    file_dir = os.path.dirname(filepath) + "/"
    return fnmatch.fnmatch(file_dir, folderpath_glob)


def get_directory_size(directory: str) -> int:
    """Return the size of a directory in bytes."""
    total_size = 0
    for dirpath, _, filenames in os.walk(directory):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size


def file_in_pythonpath(filepath) -> bool:
    """Test whether a filepath is in the same folder of a path specified in the PYTHONPATH env variable.


    Parameters
    ----------
    filepath : str
        An absolute file path.

    Returns
    -------
    boolean
        True if contained in PYTHONPATH, False otherwise. False if PYTHONPATH is not defined or empty.

    """
    pythonpath = os.environ.get("PYTHONPATH", "")
    if len(pythonpath) == 0:
        return False

    absolute_paths = [os.path.abspath(path) for path in pythonpath.split(os.pathsep)]
    return any(
        file_is_in_folder_glob(os.path.normpath(filepath), path)
        for path in absolute_paths
    )

#
# Copied from https://github.com/streamlit/streamlit/blob/1.24.0/lib/streamlit/watcher/local_sources_watcher.py
#

def get_module_paths(module: types.ModuleType) -> Set[str]:
    paths_extractors = [
        # https://docs.python.org/3/reference/datamodel.html
        # __file__ is the pathname of the file from which the module was loaded
        # if it was loaded from a file.
        # The __file__ attribute may be missing for certain types of modules
        lambda m: [m.__file__],
        # https://docs.python.org/3/reference/import.html#__spec__
        # The __spec__ attribute is set to the module spec that was used
        # when importing the module. one exception is __main__,
        # where __spec__ is set to None in some cases.
        # https://www.python.org/dev/peps/pep-0451/#id16
        # "origin" in an import context means the system
        # (or resource within a system) from which a module originates
        # ... It is up to the loader to decide on how to interpret
        # and use a module's origin, if at all.
        lambda m: [m.__spec__.origin],
        # https://www.python.org/dev/peps/pep-0420/
        # Handling of "namespace packages" in which the __path__ attribute
        # is a _NamespacePath object with a _path attribute containing
        # the various paths of the package.
        lambda m: list(m.__path__._path),
    ]

    all_paths = set()
    for extract_paths in paths_extractors:
        potential_paths = []
        try:
            potential_paths = extract_paths(module)
        except AttributeError:
            # Some modules might not have __file__ or __spec__ attributes.
            pass
        except Exception as e:
            LOGGER.warning(f"Examining the path of {module.__name__} raised: {e}")

        all_paths.update(
            [os.path.abspath(str(p)) for p in potential_paths if _is_valid_path(p)]
        )
    return all_paths


def _is_valid_path(path: Optional[str]) -> bool:
    return isinstance(path, str) and (os.path.isfile(path) or os.path.isdir(path))


#
# Original code
#

def unload_local_modules(target_dir_path: str = "."):
    """ Unload all modules that are in the target directory or in a subdirectory of it.
    It is necessary to unload modules before re-executing a script that imports the modules,
    so that the new version of the modules is loaded.
    The module unloading feature is extracted from Streamlit's LocalSourcesWatcher (https://github.com/streamlit/streamlit/blob/1.24.0/lib/streamlit/watcher/local_sources_watcher.py)
    and packaged as a standalone function.
    """
    target_dir_path = os.path.abspath(target_dir_path)
    loaded_modules = {} # filepath -> module_name

    # Copied from \`LocalSourcesWatcher.update_watched_modules()\`
    module_paths = {
        name: get_module_paths(module)
        for name, module in dict(sys.modules).items()
    }

    # Copied from \`LocalSourcesWatcher._register_necessary_watchers()\`
    for name, paths in module_paths.items():
        for path in paths:
            if file_is_in_folder_glob(path, target_dir_path) or file_in_pythonpath(path):
                loaded_modules[path] = name

    # Copied from \`LocalSourcesWatcher.on_file_changed()\`
    for module_name in loaded_modules.values():
        if module_name is not None and module_name in sys.modules:
            del sys.modules[module_name]
`;importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.3/full/pyodide.js");let M,x,F,S;async function E(e,t,o,i=3){const s=V(e,o);for(let a=0;a<i;a++){const n=a===i-1;try{return t.install.callKwargs(s,{keep_going:!0})}catch(r){if(n)throw r;console.error("Failed to install packages. Retrying...",r)}}}async function oe(e,t,o,i){console.debug("Loading Pyodide."),t("Loading Pyodide");const s=await loadPyodide({stdout:o,stderr:i});console.debug("Pyodide is loaded."),console.debug("Loading micropip"),t("Loading micropip"),await s.loadPackage("micropip");const a=s.pyimport("micropip");console.debug("micropip is loaded.");const n=[e.gradioWheelUrl,e.gradioClientWheelUrl];console.debug("Loading Gradio wheels.",n),t("Loading Gradio wheels"),await s.loadPackage(["ssl","setuptools"]),await a.add_mock_package("ffmpy","0.3.0"),await E(s,a,n),console.debug("Gradio wheels are loaded."),console.debug("Mocking os module methods."),t("Mock os module methods"),await s.runPythonAsync(`
import os

os.link = lambda src, dst: None
`),console.debug("os module methods are mocked."),console.debug("Importing gradio package."),t("Importing gradio package"),await s.runPythonAsync("import gradio"),console.debug("gradio package is imported."),console.debug("Defining a ASGI wrapper function."),t("Defining a ASGI wrapper function"),await s.runPythonAsync(`
# Based on Shiny's App.call_pyodide().
# https://github.com/rstudio/py-shiny/blob/v0.3.3/shiny/_app.py#L224-L258
async def _call_asgi_app_from_js(app_id, scope, receive, send):
	# TODO: Pretty sure there are objects that need to be destroy()'d here?
	scope = scope.to_py()

	# ASGI requires some values to be byte strings, not character strings. Those are
	# not that easy to create in JavaScript, so we let the JS side pass us strings
	# and we convert them to bytes here.
	if "headers" in scope:
			# JS doesn't have \`bytes\` so we pass as strings and convert here
			scope["headers"] = [
					[value.encode("latin-1") for value in header]
					for header in scope["headers"]
			]
	if "query_string" in scope and scope["query_string"]:
			scope["query_string"] = scope["query_string"].encode("latin-1")
	if "raw_path" in scope and scope["raw_path"]:
			scope["raw_path"] = scope["raw_path"].encode("latin-1")

	async def rcv():
			event = await receive()
			py_event = event.to_py()
			if "body" in py_event:
					if isinstance(py_event["body"], memoryview):
							py_event["body"] = py_event["body"].tobytes()
			return py_event

	async def snd(event):
			await send(event)

	app = gradio.wasm_utils.get_registered_app(app_id)
	if app is None:
		raise RuntimeError("Gradio app has not been launched.")

	await app(scope, rcv, snd)
`),M=s.globals.get("_call_asgi_app_from_js"),console.debug("The ASGI wrapper function is defined."),console.debug("Mocking async libraries."),t("Mocking async libraries"),await s.runPythonAsync(`
async def mocked_anyio_to_thread_run_sync(func, *args, cancellable=False, limiter=None):
	return func(*args)

import anyio.to_thread
anyio.to_thread.run_sync = mocked_anyio_to_thread_run_sync
	`),console.debug("Async libraries are mocked."),console.debug("Setting up Python utility functions."),t("Setting up Python utility functions"),await s.runPythonAsync(ee),x=s.globals.get("_run_code"),F=s.globals.get("_run_script"),await s.runPythonAsync(te),S=s.globals.get("unload_local_modules"),console.debug("Python utility functions are set up."),t("Initialization completed");const r=new Z(s);return{pyodide:s,micropip:a,codeCompleter:r}}async function ae(e,t,o,i,s,a){const n=v(o);console.debug("Creating a home directory for the app.",{appId:o,appHomeDir:n}),e.FS.mkdir(n),console.debug("Mounting files.",i.files),s("Mounting files");const r=[];await Promise.all(Object.keys(i.files).map(async u=>{const f=i.files[u];let d;"url"in f?(console.debug(`Fetch a file from ${f.url}`),d=await fetch(f.url).then(y=>y.arrayBuffer()).then(y=>new Uint8Array(y))):d=f.data;const{opts:m}=i.files[u],g=w(o,u);console.debug(`Write a file "${g}"`),N(e,g,d,m),typeof d=="string"&&u.endsWith(".py")&&r.push(d)})),console.debug("Files are mounted."),console.debug("Installing packages.",i.requirements),s("Installing packages"),await E(e,t,i.requirements),console.debug("Packages are installed."),console.debug("Auto-loading modules.");const l=await Promise.all(r.map(u=>e.loadPackagesFromImports(u))),p=new Set(l.flat()),c=Array.from(p);c.length>0&&a(c);const h=c.map(u=>u.name);console.debug("Modules are auto-loaded.",c),(i.requirements.includes("matplotlib")||h.includes("matplotlib"))&&(console.debug("Setting matplotlib backend."),s("Setting matplotlib backend"),await e.runPythonAsync(`
try:
	import matplotlib
	matplotlib.use("agg")
except ImportError:
	pass
`),console.debug("matplotlib backend is set.")),s("App is now loaded")}const O=self;"postMessage"in O?D(O):O.onconnect=e=>{const t=e.ports[0];D(t),t.start()};let A;function D(e){const t=X(8);console.debug("Set up a new app.",{appId:t});const o=l=>{e.postMessage({type:"progress-update",data:{log:l}})},i=l=>{console.log(l),e.postMessage({type:"stdout",data:{output:l}})},s=l=>{console.error(l),e.postMessage({type:"stderr",data:{output:l}})},a=l=>{console.error("Python error:",l),e.postMessage({type:"python-error",data:{traceback:l}})},n=l=>{const p={type:"modules-auto-loaded",data:{packages:l}};e.postMessage(p)};let r;e.onmessage=async function(l){const p=l.data;console.debug("worker.onmessage",p);const c=l.ports[0];try{if(p.type==="init-env"){A==null?A=oe(p.data,o,i,s):o("Pyodide environment initialization is ongoing in another session"),A.then(()=>{const d={type:"reply:success",data:null};c.postMessage(d)}).catch(d=>{const m={type:"reply:error",error:d};c.postMessage(m)});return}if(A==null)throw new Error("Pyodide Initialization is not started.");const{pyodide:h,micropip:u,codeCompleter:f}=await A;if(h.pyimport("gradio").wasm_utils.register_error_traceback_callback(t,a),p.type==="init-app"){r=ae(h,u,t,p.data,o,n);const d={type:"reply:success",data:null};c.postMessage(d);return}if(r==null)throw new Error("App initialization is not started.");switch(await r,p.type){case"echo":{const d={type:"reply:success",data:p.data};c.postMessage(d);break}case"run-python-code":{S(),console.debug("Auto install the requirements");const d=await h.loadPackagesFromImports(p.data.code);d.length>0&&n(d),console.debug("Modules are auto-loaded.",d),await x(t,v(t),p.data.code);const m={type:"reply:success",data:null};c.postMessage(m);break}case"run-python-file":{S(),await F(t,v(t),p.data.path);const d={type:"reply:success",data:null};c.postMessage(d);break}case"asgi-request":{console.debug("ASGI request",p.data),K(M.bind(null,t),p.data.scope,c);break}case"file:write":{const{path:d,data:m,opts:g}=p.data;if(typeof m=="string"&&d.endsWith(".py")){console.debug(`Auto install the requirements in ${d}`);const k=await h.loadPackagesFromImports(m);k.length>0&&n(k),console.debug("Modules are auto-loaded.",k)}const y=w(t,d);console.debug(`Write a file "${y}"`),N(h,y,m,g);const C={type:"reply:success",data:null};c.postMessage(C);break}case"file:rename":{const{oldPath:d,newPath:m}=p.data,g=w(t,d),y=w(t,m);console.debug(`Rename "${g}" to ${y}`),Y(h,g,y);const C={type:"reply:success",data:null};c.postMessage(C);break}case"file:unlink":{const{path:d}=p.data,m=w(t,d);console.debug(`Remove "${m}`),h.FS.unlink(m);const g={type:"reply:success",data:null};c.postMessage(g);break}case"install":{const{requirements:d}=p.data;console.debug("Install the requirements:",d),z(d),await E(h,u,d).then(()=>{if(d.includes("matplotlib"))return h.runPythonAsync(`
try:
	import matplotlib
	matplotlib.use("agg")
except ImportError:
	pass
`)}).then(()=>{console.debug("Successfully installed");const m={type:"reply:success",data:null};c.postMessage(m)});break}case"code-completion":{const d=p.data,m={type:"reply:success",data:await f.getCodeCompletions(d)};c.postMessage(m);break}}}catch(h){if(console.error(h),!(h instanceof Error))throw h;const u=new Error(h.message);u.name=h.name,u.stack=h.stack;const f={type:"reply:error",error:u};c.postMessage(f)}}}})();
//# sourceMappingURL=webworker-BsZ7XNFH.js.map
