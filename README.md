# cbot
The basic idea is to let Discord users to write their own scripts for an isolated sandboxed JS environment. The bot is in Python and uses STPyV8 to run a V8 (Google's JS engine) process for each user. The environment takes care of isolating users but also provides safe escape hatches as builtins for persistent state, network, macros etc. There are 3 kinds of commands so far. A tech savvy user should be able to quickly do stuff under the hood, but a casual user who only wants to use a script should be able to do that easily as well without a PhD in CS.

(Put Discord token in `{repo}/token.txt`)

## Commands

### $-commands: REPL
`$` acts just like a JS REPL, executing the written code as is. Each user gets their own private JS thread that lives as long as the server is alive, so if the server is shut down everything in the current session is lost. However, `this.s` is a persistently stored object that is stored and retrieved from disk. Put any long-term data into `this.s`. The results of the last expression are returned to Discord, and the print buffer is also drained and shown.

Example:
```
$var sum = (a, b) => print(a+b); sum(5, 6);
Reply: 11
```

The JS Fetch API is disabled, instead there is a safe network request function `this.req(url)` that return the text of the reply (you can then run `JSON.parse` on the text etc.). Unlike JS Fetch, `this.req()` is a regular old synchronous call. It asks Python to run the request instead and only allows URLs from an allow list.

### #-commands: Function Call, Export, and Macros
`#func arg1 arg2 arg3...` is equivalent to `$func(arg1, arg2, arg3)` but is less typing. Importantly, strings need to be quoted since `#` will not do any interpretation. (`func` can also be a macro, more on that later). For example,

`#ddgsearch "cats"` is the same as `$ddgsearch("cats")`, while `#ddgsearch cats` becomes `#ddgsearch(cats)` which tries to look for a variable called `cats`.

`#` can also run "public" functions. By doing `#@{user} func args...` you can run `func(args...)` **as if you were the mentioned user, with their state and everything**. However, only functions that have been exported using `def_export("func_name")` can be run this way, and `$` cannot run public functions. This lets you create a public interface for your code that other people can use. For example, if `user1` made cheatcodes stored in their internal `this.s` and wanted others to guess using a `guess` function that reads the state and checks if a guess hits (and marks it used if it does), they would run

```
$def_export("guess")
```

Then other users can run

```
#@user1 guess "I know my game"
```

to guess cheatcodes. This is rather wordy and can be solved with a `def_macro("macro_name", "macro_var", "text")` macro, which works exactly like a C `#define` with plain text substitution, no JS or Python semantics involved. When evaluating a `#` command, the macro list is checked first. For example, the above can be simplified using this

```
def_macro("g", "Guess", "#<@userid> guess \"Guess\"")
```
Here the macro is constructing a public export `#`-call that's easier to type. Macros can currently have strictly one token name and one token arg (whitespaces will be stripped), so everything after the macro name and then a whitespace will be parsed as the macro var. You can query your user_id (a big int) using the `this.userid` builtin.

Which can then be used like 
```
#g I know my game
```
(here `Guess=I know my game`, which makes the result of the macro `#<@userid> guess "I know my game"`). Which is finally a "simple" command that an end user can use easily. Macro commands can create any other kind of command.

### &-commands: Read and Write
Use `&+filename code` to save code to a named file. Use `&*filename` to read the file and display the contents on Discord. Use `&&filename` to read and execute a file - the intention here is to use it to load a library previously saved using `&+`, or manually added by the bot author to the backend. All user code is stored in `{bot dir}/usercode/` on the backend, you can just place a file with JS code there and then have users load it using `&&`. This lets you make libraries either from Discord itself or in a better editor like VSCode. Note that library files are not per-user so someone else could conceivably erase your lib. So you probably want to prefix it with an identifying name.

For example

```
&+testlib
function lmao() {
    print("lmao from testlib");
}
```

Someone else can load this lib using 

```
&&testlib
```

Then run the function

```
#lmao
Reply: lmao from testlib
```

### Builtins
A summary of the builtins exported from Python (more coming later)
- `this.s`: a persistent JS object whose data will be written to disk after every command execution (wasteful, but oh well) and reloaded on server start. You can store persistent state in this, like `this.s["cheatcodes"] = ["code1", "code2", "code3"]`. Avoid storing functions as it's first converted into a Python dictionary then serialized (using pickle) to disk.
- `this.req(url) -> string|undefined` does a GET request to the url and returns the result string. Only urls in the allow list will go through.
- `this.userid` your user ID as a string (because JS ints are not ints...), can be used to construct Discord mentions like `<@userid>`
- `def_export("func_name")` publicly exports a function allowing other users to call it using `#@userid`
- `def_macro("macro_name", "macro_var", "text")` creates a macro called `macro_name` that can be called using `#`. `macro_var` will be plain text substituted in `text`, then whatever comes out will be run as is (so macros can create `$` and `&` commands too). Macros are private to each user but you can distribute them using a library file.