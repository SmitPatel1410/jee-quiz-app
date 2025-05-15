const quizTitle = document.getElementById("quizTitle");
const questionContainer = document.getElementById("questionContainer");
const nextBtn = document.getElementById("nextBtn");
const timeLeftDisplay = document.getElementById("timeLeft");

let currentQuestion = 0;
let score = 0;
let timer;
let timeLeft = 30;
let questions = [];

quizTitle.textContent = "Dynamic Quiz";

fetch("/api/questions")
  .then((res) => res.json())
  .then((data) => {
    questions = data;
    if (questions.length > 0) {
      loadQuestion();
    } else {
      questionContainer.innerHTML = "<p>No quiz questions available.</p>";
      nextBtn.disabled = true;
    }
  })
  .catch((err) => {
    questionContainer.innerHTML = "<p>Error loading quiz questions.</p>";
    console.error(err);
  });

function loadQuestion() {
  clearInterval(timer); // Clear any previous timer
  timeLeft = 30;
  updateTimer();
  timer = setInterval(countdown, 1000);

  const q = questions[currentQuestion];
  questionContainer.innerHTML = `
    <div class="question">
      <h3>${q.q}</h3>
      <div class="options">
        ${q.options.map((opt, i) => `
          <label>
            <input type="radio" name="answer" value="${i}" /> ${opt}
          </label>
        `).join("")}
      </div>
    </div>
  `;
}

function countdown() {
  timeLeft--;
  updateTimer();
  if (timeLeft === 0) {
    alert("Time's up! Moving to the next question.");
    nextBtn.click(); // Auto move
  }
}

function updateTimer() {
  timeLeftDisplay.textContent = timeLeft;
}

nextBtn.addEventListener("click", () => {
  clearInterval(timer);

  const selected = document.querySelector("input[name='answer']:checked");
  const answer = selected ? parseInt(selected.value) : -1;
  if (answer === questions[currentQuestion].answer) score++;

  currentQuestion++;
  if (currentQuestion < questions.length) {
    loadQuestion();
  } else {
    localStorage.setItem("quizScore", `${score}/${questions.length}`);
    window.location.href = "results";
  }
});
