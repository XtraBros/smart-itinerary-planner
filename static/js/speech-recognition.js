if ("webkitSpeechRecognition" in window) {
      let speechRecognition = new webkitSpeechRecognition();
      let final_transcript = "";

      speechRecognition.continuous = true;
      //speechRecognition.started = false;
      speechRecognition.interimResults = true;
      speechRecognition.lang = document.querySelector("#select_dialect").value;

      speechRecognition.onstart = () => {
              //document.querySelector("#status").style.display = "block";
            };
      speechRecognition.onerror = (event) => {
              //document.querySelector("#status").style.display = "none";
              console.log(`Speech Recognition Error: ${event.error}`);
            };
      speechRecognition.onend = () => {
              //document.querySelector("#status").style.display = "none";
              console.log("Speech Recognition Ended");
            };

      speechRecognition.onresult = (event) => {
              let interim_transcript = "";

              for (let i = event.resultIndex; i < event.results.length; ++i) {
                        if (event.results[i].isFinal) {
                                    final_transcript += event.results[i][0].transcript;
                                  } else {
                                              interim_transcript += event.results[i][0].transcript;
                                            }
                      }
              document.querySelector("#chatbot-input").value = final_transcript;
              //document.querySelector("#final").innerHTML = final_transcript;
              //document.querySelector("#interim").innerHTML = interim_transcript;
            };

      startVoiceInput = () => {
          var recordIcon = document.getElementById('record');
          if (!recordIcon.classList.contains('fa-microphone')){
              recordIcon.classList.remove('fa-circle');
              recordIcon.classList.add('fa-microphone');
              speechRecognition.stop();
          }
          else {
              recordIcon.classList.remove('fa-microphone');
              recordIcon.classList.add('fa-circle');
              speechRecognition.start();
          }
      };

      //document.querySelector("#start").onclick = () => {
      //        speechRecognition.start();
      //      };
      //document.querySelector("#stop").onclick = () => {
      //        speechRecognition.stop();
      //      };
} else {
      console.log("Speech Recognition Not Available");
}
