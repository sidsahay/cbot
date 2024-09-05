var stdout = [];

function print(s) {
    stdout.push(s);
}

function reset_stdout() {
    stdout = [];
}

function random_int(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function d(n, v) {
    let res = 0;
    for (let i = 0; i < n; i++) {
        let roll = random_int(n, v);
        print(`1d${v} rolled ${roll}`)
        res += roll;
    }
    return res;
}

var new_macros = [];

function def_macro(macro_name, macro_var, text) {
    print(`Defined macro ${macro_name}`);
    new_macros.push([macro_name, macro_var, text]);
}

function reset_macros() {
    new_macros = [];
}

var new_exports = [];

function def_export(func_name) {
    print(`Exported function ${func_name}()`);
    new_exports.push(func_name);
}

function reset_exports() {
    new_exports = [];
}

function gen_text(prompt, max_tokens=200, suffix=" Answer in 200 words or less") {
    let p = prompt + suffix;
    return this.gen(prompt, max_tokens)["text"];
}

def_macro("gen", "Text", '$gen_text("Text")')