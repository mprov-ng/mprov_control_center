window.onload = function textarea_tab(){
  elements = document.getElementsByTagName('textarea');

  for (let id=0; id < elements.length; id++){

    console.log(id)
    elements[id].addEventListener('keydown', function(e) {
      
      if (e.key == 'Tab') {
        e.preventDefault();
        var start = this.selectionStart;
        var end = this.selectionEnd;

        // set textarea value to: text before caret + tab + text after caret
        this.value = this.value.substring(0, start) +
          "\t" + this.value.substring(end);

        // put caret at right position again
        this.selectionStart =
          this.selectionEnd = start + 1;
      }
    });
  }
}
