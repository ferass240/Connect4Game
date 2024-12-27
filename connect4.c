#include <math.h>
#include <time.h>
#include <stdio.h>
#include <wchar.h>
#include <unistd.h>  // for sleep()
#include <string.h>

#include <assert.h>
#include <locale.h>
#include <stdlib.h>
#include <inttypes.h>
#include <sys/mman.h>   // For PROT_WRITE and mmap
#include <sys/stat.h>   // For shm_open
#include <fcntl.h>      // For O_CREAT, O_RDWR
#include <unistd.h>     // For ftruncate and close

/* Engine, AI, and Display Parameters */
#define SHM_NAME "/bot_move"  // Name of the shared memory segment
#define SHM_SIZE 2*sizeof(int)     // Size of the shared memory (size of an int)

//#define FILE_PATH "detected_disc.txt"


#define SHM_NAME_NEW_DISC "/new_disc_shared_memory"
#define SHM_NEW_DISC_SIZE 8*sizeof(int) 
        
// const char *SHM_NAME_NEW_DISC = "/new_disc_shared_memory";
int shm_fd_new_disc;
void *shm_ptr_new_disc;


#define WINNER_FILE "winner.txt"  // The file where the winner will be written

enum player_type{
    PLAYER_HUMAN, 
    PLAYER_AI
    };
// Board dimensions (must be <= 64 slots)
#define CONNECT4_WIDTH  7
#define CONNECT4_HEIGHT 6

// AI constraints
#define CONNECT4_MEMORY_SIZE  (32UL * 1024 * 1024)
#define CONNECT4_MAX_PLAYOUTS (512UL * 1024)

// AI parameters
#define CONNECT4_C          2.0f
#define CONNECT4_SCORE_WIN  1.0f
#define CONNECT4_SCORE_DRAW 0.1f

// Display colors and size
#define COLOR_PLAYER0   9
#define COLOR_PLAYER1   12
#define COLOR_MARKER    11
#define COLOR_BLANK     8
#define DISPLAY_INDENT  ((80 - CONNECT4_WIDTH * 6) / 2)

/* OS Terminal/Console API */

#define RIGHT_HALF_BLOCK 0x2590u
#define LEFT_HALF_BLOCK  0x258cu
#define FULL_BLOCK       0x2588u
#define MIDDLE_DOT       0x00B7u

static void os_init(void);
static void os_color(int);
static void os_reset_terminal(void);
static void os_finish(void);

#if defined(__unix__) || defined(__unix) || defined(__APPLE__)
#include <unistd.h>
#include <sys/time.h>

static void
os_init(void)
{
    // nothing
}


static void
os_color(int color)
{
    int base = color & 0x8 ? 90 : 30;
    const char *bold = color & 0x8 ? ";1" : "";
    if (color)
        wprintf(L"\x1b[%d%sm", base + (color & 0x7), bold);
    else
        wprintf(L"\x1b[0m");
}

static void
os_reset_terminal(void)
{
    wprintf(L"\x1b[2J\x1b[H");
}

static void
os_finish(void)
{
    // nothing
}

#elif _WIN32
#define _CRT_STDIO_ISO_WIDE_SPECIFIERS
#include <io.h>
#include <fcntl.h>
#include <wchar.h>
#include <windows.h>

static void
os_init(void)
{
    _setmode(_fileno(stdout), _O_U16TEXT);
}

static void
os_color(int color)
{
    WORD bits = 0;
    if (!color || color & 0x1)
        bits |= FOREGROUND_RED;
    if (!color || color & 0x2)
        bits |= FOREGROUND_GREEN;
    if (!color || color & 0x4)
        bits |= FOREGROUND_BLUE;
    if (color & 0x8)
        bits |= FOREGROUND_INTENSITY;
    SetConsoleTextAttribute(GetStdHandle(STD_OUTPUT_HANDLE), bits);
}

static void
os_reset_terminal(void)
{
    HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO info;
    GetConsoleScreenBufferInfo(out, &info);
    info.dwCursorPosition.Y = 0;
    info.dwCursorPosition.X = 0;
    COORD origin = {0, 0};
    DWORD dummy;
    FillConsoleOutputCharacter(out, ' ', (DWORD)-1, origin, &dummy);
    SetConsoleCursorPosition(out, info.dwCursorPosition);
}

static void
os_finish(void)
{
    system("pause");
}
#endif

/* Pseudo-Random Number Generator */

static uint64_t
rotl(const uint64_t x, int k)
{
    return (x << k) | (x >> (64 - k));
}

static uint64_t
xoroshiro128plus(uint64_t *s)
{
    const uint64_t s0 = s[0];
    uint64_t s1 = s[1];
    const uint64_t result = s0 + s1;
    s1 ^= s0;
    s[0] = rotl(s0, 55) ^ s1 ^ (s1 << 14); // a, b
    s[1] = rotl(s1, 36); // c
    return result;
}

static uint64_t
splitmix64(uint64_t *x)
{
    uint64_t z = (*x += UINT64_C(0x9E3779B97F4A7C15));
    z = (z ^ (z >> 30)) * UINT64_C(0xBF58476D1CE4E5B9);
    z = (z ^ (z >> 27)) * UINT64_C(0x94D049BB133111EB);
    return z ^ (z >> 31);
}

/* Connect Four Engine */

static uint64_t connect4_wins[CONNECT4_WIDTH * CONNECT4_HEIGHT][16];

/**
 * Fills out the bitboard tables. Must be called before any other
 * connect4 function.
 */
static void
connect4_startup(void)
{
    static int delta[] = {
        -1, -1, -1,  0, -1,  1, 0,  1, 0, -1, 1,  1, 1,  0, 1, -1,
    };
    for (int y = 0; y < CONNECT4_HEIGHT; y++) {
        for (int x = 0; x < CONNECT4_WIDTH; x++) {
            int i = 0;
            for (int d = 0; d < 8; d++) {
                for (int s = -3; s <= 0; s++) {
                    uint64_t mask = 0;
                    int valid = 1;
                    for (int p = s; p < s + 4; p++) {
                        int xx = x + delta[d * 2 + 0] * p;
                        int yy = y + delta[d * 2 + 1] * p;
                        int shift = yy * CONNECT4_WIDTH + xx;
                        if (xx < 0 || xx >= CONNECT4_WIDTH ||
                            yy < 0 || yy >= CONNECT4_HEIGHT)
                            valid = 0;
                        else
                            mask |= UINT64_C(1) << shift;
                    }
                    if (valid)
                        connect4_wins[y * CONNECT4_WIDTH + x][i++] = mask;
                }
            }
        }
    }
}

enum connect4_result {
    CONNECT4_RESULT_UNRESOLVED,
    CONNECT4_RESULT_DRAW,
    CONNECT4_RESULT_WIN,
};

static enum connect4_result
connect4_check(uint64_t who, uint64_t opponent, int position, uint64_t *how)
{
    for (int i = 0; i < 16; i++) {
        uint64_t mask = connect4_wins[position][i];
        if (mask && (mask & who) == mask) {
            *how = mask;
            return CONNECT4_RESULT_WIN;
        }
    }
    *how = 0;
    if ((who | opponent) == UINT64_C(0x3ffffffffff))
        return CONNECT4_RESULT_DRAW;
    return CONNECT4_RESULT_UNRESOLVED;
}

static int
connect4_valid(uint64_t taken, int play)
{
    uint64_t top = UINT64_C(1) << play;
    return play >= 0 && play < CONNECT4_WIDTH && !(top & taken) ? 1 : 0;
}

static int
connect4_drop(uint64_t taken, int play)
{
    int position = play;
    for (int i = 1; i < CONNECT4_HEIGHT; i++) {
        position += CONNECT4_WIDTH;
        uint64_t mask = UINT64_C(1) << position;
        if (mask & taken)
            return position - CONNECT4_WIDTH;
    }
    return position;
}

#define CONNECT4_NULL ((uint32_t)-1)
#define CONNECT4_WIN0 ((uint32_t)-2)
#define CONNECT4_WIN1 ((uint32_t)-3)
#define CONNECT4_DRAW ((uint32_t)-4)
struct connect4_ai {
    uint64_t state[2];
    uint64_t rng[2];
    uint32_t nodes_available;
    uint32_t nodes_allocated;
    uint32_t root;
    uint32_t free;
    int turn;
    struct connect4_node {
        uint32_t next[CONNECT4_WIDTH];
        uint32_t playouts[CONNECT4_WIDTH];
        float    score[CONNECT4_WIDTH];
    } nodes[];
};

static uint32_t
connect4_alloc(struct connect4_ai *c)
{
    uint32_t node = c->free;
    if (node != CONNECT4_NULL) {
        struct connect4_node *n = c->nodes + node;
        c->nodes_allocated++;
        c->free = n->next[0];
        for (int i = 0; i < CONNECT4_WIDTH; i++) {
            n->next[i] = CONNECT4_NULL;
            n->playouts[i] = 0;
            n->score[i] = 0;
        }
    }
    return node;
}

static void
connect4_free(struct connect4_ai *c, uint32_t node)
{
    if (node < CONNECT4_DRAW) {
        struct connect4_node *n = c->nodes + node;
        c->nodes_allocated--;
        for (int i = 0; i < CONNECT4_WIDTH; i++)
            connect4_free(c, n->next[i]);
        n->next[0] = c->free;
        c->free = node;
    }
}

static struct connect4_ai *
connect4_init(void *buf, size_t bufsize)
{
    struct connect4_ai *c = buf;
    c->nodes_available = (bufsize - sizeof(*c)) / sizeof(c->nodes[0]);
    c->nodes_allocated = 0;
    c->state[0] = 0;
    c->state[1] = 0;
    c->turn = 0;
    c->free = 0;
    static uint64_t seed;
    seed ^= time(0);
    c->rng[0] = splitmix64(&seed);
    c->rng[1] = splitmix64(&seed);
    for (uint32_t i = 0; i < c->nodes_available - 1; i++)
        c->nodes[i].next[0] = i + 1;
    c->nodes[c->nodes_available - 1].next[0] = CONNECT4_NULL;
    c->root = connect4_alloc(c);
    return c;
}


const char *file_path = "/tmp/bot_move.txt";

// Add this function to write the bot's move to a file
void write_bot_move_to_shm(int move) {
    int fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (fd == -1) {
        perror("shm_open failed");
        return;
    }
    ftruncate(fd, 1);
    char *ptr = mmap(0, 1, PROT_WRITE, MAP_SHARED, fd, 0);
    if (ptr == MAP_FAILED) {
        perror("mmap failed");
        close(fd);
        return;
    }
    ptr[0] = move + 1; // Write the move
    munmap(ptr, 1);
    close(fd);
}
// Function to delete the file if it exists
int delete_bot_move_file() {
    // Check if the file exists
    if (remove(file_path) == 0) {
        return 1;
    } else {
        return 0;
    }
}

static void
connect4_advance(struct connect4_ai *c, int play)
{
    assert(connect4_valid(c->state[0] | c->state[1], play));
    int position = connect4_drop(c->state[0] | c->state[1], play);
    c->state[c->turn] |= UINT64_C(1) << position;
    c->turn = !c->turn;
    struct connect4_node *n = c->nodes + c->root;
    uint32_t old_root = c->root;
    c->root = n->next[play];
    n->next[play] = CONNECT4_NULL;
    connect4_free(c, old_root);
    if (c->root == CONNECT4_NULL)
        c->root = connect4_alloc(c);
}



static int
connect4_playout(struct connect4_ai *c,
                 uint32_t node,
                 const uint64_t state[2],
                 int turn)
{
    if (node == CONNECT4_WIN0)
        return 0;
    else if (node == CONNECT4_WIN1)
        return 1;
    else if (node == CONNECT4_DRAW)
        return 2;
    assert(node != CONNECT4_NULL);

    struct connect4_node *n = c->nodes + node;
    int options[CONNECT4_WIDTH];
    int noptions = 0;
    uint64_t taken = state[0] | state[1];
    for (int i = 0; i < CONNECT4_WIDTH; i++)
        if (n->next[i] == CONNECT4_NULL && connect4_valid(taken, i))
            options[noptions++] = i;
    int play;
    if (noptions == 0) {
        /* Select a move using upper confidence bound (UCB1). */
        uint32_t total = 0;
        for (int i = 0; i < CONNECT4_WIDTH; i++)
            if (connect4_valid(taken, i))
                total += n->playouts[i];
        float best_value = -INFINITY;
        float numerator = CONNECT4_C * logf((float)total);
        int best[CONNECT4_WIDTH];
        int nbest = 0;
        for (int i = 0; i < CONNECT4_WIDTH; i++) {
            if (connect4_valid(taken, i)) {
                assert(n->playouts[i]);
                total += n->playouts[i];
                float mean = n->score[i] / n->playouts[i];
                float value = mean + sqrtf(numerator / n->playouts[i]);
                if (value > best_value) {
                    best_value = value;
                    nbest = 1;
                    best[0] = i;
                } else if (value == best_value) {
                    best[nbest++] = i;
                }
            }
        }
        play = nbest == 1 ? best[0] : best[xoroshiro128plus(c->rng) % nbest];
        int position = connect4_drop(state[0] | state[1], play);
        uint64_t place = UINT64_C(1) << position;
        uint64_t copy[2] = {state[0], state[1]};
        copy[turn] |= place;
        int winner = connect4_playout(c, n->next[play], copy, !turn);
        if (winner >= 0)
            n->playouts[play]++;
        if (winner == turn)
            n->score[play] += CONNECT4_SCORE_WIN;
        else if (winner == 2)
            n->score[play] += CONNECT4_SCORE_DRAW;
        //write_winner_to_file(winner);
        //sleep(3);
        return winner;
    } else {
        /* Select a random, unplayed move. */
        if (noptions == 1)
            play = options[0];
        else play = options[xoroshiro128plus(c->rng) % noptions];
            
        int position = connect4_drop(state[0] | state[1], play);
        uint64_t place = UINT64_C(1) << position;
        uint64_t copy[2] = {state[0], state[1]};
        copy[turn] |= place;
        uint64_t dummy;
        switch (connect4_check(copy[turn], copy[!turn], position, &dummy)) {
            case CONNECT4_RESULT_DRAW:
                n->playouts[play]++;
                n->score[play] += CONNECT4_SCORE_DRAW;
                n->next[play] = CONNECT4_DRAW;
                return 2;
            case CONNECT4_RESULT_WIN:
                n->playouts[play]++;
                n->score[play] += CONNECT4_SCORE_WIN;
                n->next[play] = turn ? CONNECT4_WIN1 : CONNECT4_WIN0;
                return turn;
            case CONNECT4_RESULT_UNRESOLVED:
                n->next[play] = connect4_alloc(c);
                if (n->next[play] == CONNECT4_NULL)
                    return -1; // out of memory
                n->playouts[play]++;
                break;
        }
        /* Play out rest of game without node allocation. */
        int original_play = play;
        int original_turn = turn;
        for (;;) {
            turn = !turn;
            int options[CONNECT4_WIDTH];
            int noptions = 0;
            uint64_t taken = copy[0] | copy[1];
            for (int i = 0; i < CONNECT4_WIDTH; i++)
                if (connect4_valid(taken, i))
                    options[noptions++] = i;
            int play;
            if (noptions == 1)
                play = options[0];
            else
                play = options[xoroshiro128plus(c->rng) % noptions];
            int position = connect4_drop(copy[0] | copy[1], play);
            uint64_t place = UINT64_C(1) << position;
            copy[turn] |= place;
            uint64_t x;
            switch (connect4_check(copy[turn], copy[!turn], position, &x)) {
                case CONNECT4_RESULT_UNRESOLVED:
                    break;
                case CONNECT4_RESULT_DRAW:
                    n->score[original_play] += CONNECT4_SCORE_DRAW;
                    return 2;
                case CONNECT4_RESULT_WIN:
                    if (turn == original_turn)
                        n->score[original_play] += CONNECT4_SCORE_WIN;
                    return turn;
            }
            turn = !turn;
        }
    }
}

static int
connect4_playout_many(struct connect4_ai *c, uint32_t count)
{
    for (uint32_t i = 0; i < count; i++)
        if (connect4_playout(c, c->root, c->state, c->turn) == -1)
            break;
    struct connect4_node *n = c->nodes + c->root;
    double best_ratio = -INFINITY;
    int best_move = -1;
    for (int i = 0; i < CONNECT4_WIDTH; i++)
        if (n->playouts[i]) {
            double ratio = n->score[i] / (double)n->playouts[i];
            if (ratio > best_ratio) {
                best_ratio = ratio;
                best_move = i;
            }
        }
    return best_move;
}

/* Terminal/Console User Interface */

static void
connect4_display(uint64_t p0, uint64_t p1, uint64_t highlight)
{
    os_reset_terminal();
    wprintf(L"%*s", DISPLAY_INDENT, "");
    for (int w = 0; w < CONNECT4_WIDTH; w++)
        wprintf(L" %-5d", w + 1);
    wprintf(L"\n\n");
    for (int h = 0; h < CONNECT4_HEIGHT; h++) {
        for (int b = 0; b < 2; b++) {
            wprintf(L"%*s", DISPLAY_INDENT, "");
            for (int w = 0; w < CONNECT4_WIDTH; w++) {
                int s = h * CONNECT4_WIDTH + w;
                int mark = (highlight >> s) & 1;
                int color = 0;
                if ((p0 >> s) & 1)
                    color = COLOR_PLAYER0;
                else if ((p1 >> s) & 1)
                    color = COLOR_PLAYER1;
                if (color) {
                    os_color(mark ? COLOR_MARKER : color);
                    fputwc(RIGHT_HALF_BLOCK, stdout);
                    if (mark)
                        os_color(0);
                    os_color(color);
                    fputwc(FULL_BLOCK, stdout);
                    fputwc(FULL_BLOCK, stdout);
                    if (mark) {
                        os_color(0);
                        os_color(COLOR_MARKER);
                    }
                    fputwc(LEFT_HALF_BLOCK, stdout);
                    os_color(0);
                    wprintf(L"  ");
                } else {
                    os_color(COLOR_BLANK);
                    wprintf(L" ");
                    fputwc(MIDDLE_DOT, stdout);
                    fputwc(MIDDLE_DOT, stdout);
                    os_color(0);
                    wprintf(L"   ");
                }
            }
            fputwc(L'\n', stdout);
        }
        fputwc(L'\n', stdout);
    }
}

struct connect4_game {
    uint64_t state[2];
    uint64_t marker;
    int turn;
    int winner;
    unsigned nplays;
    int8_t plays[CONNECT4_WIDTH * CONNECT4_HEIGHT];
};

static void
connect4_game_init(struct connect4_game *g)
{
    g->state[0] = 0;
    g->state[1] = 0;
    g->marker = 0;
    g->turn = 0;
    g->winner = -1;
    g->nplays = 0;
}

static enum connect4_result
connect4_game_move(struct connect4_game *g, int play)
{
    g->plays[g->nplays++] = (int8_t)play;
    int position = connect4_drop(g->state[0] | g->state[1], play);
    g->state[g->turn] |= UINT64_C(1) << position;
    uint64_t who = g->state[g->turn];
    uint64_t opponent = g->state[!g->turn];
    switch (connect4_check(who, opponent, position, &g->marker)) {
        case CONNECT4_RESULT_UNRESOLVED:
            g->marker = UINT64_C(1) << position;
            g->turn = !g->turn;
            return CONNECT4_RESULT_UNRESOLVED;
        case CONNECT4_RESULT_DRAW:
            g->winner = 2;
            return CONNECT4_RESULT_DRAW;
        case CONNECT4_RESULT_WIN:
            g->winner = g->turn;
            return CONNECT4_RESULT_WIN;
    }
    abort();
}

typedef int (*connect4_player)(const struct connect4_game *, void *);


static int
player_human(const struct connect4_game *g, void *arg);
static int
player_ai(const struct connect4_game *g, void *arg);

static int connect4_game_run(struct connect4_game *g,
                       connect4_player players[2],
                       void *args[2],
                       int display)
{

    if (display) {
        connect4_display(g->state[0], g->state[1], g->marker);
    }

    for (;;) {
        printf("Current Turn: %d\n", g->turn);  // Debug output

        int play = players[g->turn](g, args[g->turn]); // Get the current player's move

        // Write AI moves to shared memory in real-time
        if (players[g->turn] == player_ai) {
            write_bot_move_to_shm(play);  // Write bot move to shared memory
            printf("Player %d (AI) move written to shared memory: %d\n", g->turn + 1, play);
        }

        // Apply the move to the game
        enum connect4_result r = connect4_game_move(g, play);

        // Display the game state if enabled
        if (display) {
            connect4_display(g->state[0], g->state[1], g->marker);
        }

        
        
    }
}

/**int read_new_disc_from_file() {
    FILE *file = fopen(FILE_PATH, "r");
    if (file == NULL) {
        perror("Failed to open file");
        return -1;
    }

    int detected_column;
    if (fscanf(file, "%d", &detected_column) == 1) {
        // After reading the value, clear the contents of the file
        sleep(3);
        fclose(file);

        // Open the file in write mode to clear its contents
        file = fopen(FILE_PATH, "w");
        if (file == NULL) {
            perror("Failed to open file for clearing");
            return -1;
        }
        fclose(file);  // Close it after clearing

        return detected_column;
    } else {
        fclose(file);
        return -1; // Return -1 if no valid data is found
    }
}**/





// Function to read the value from shared memory
int read_from_shared_memory(void *shm_ptr_new_disc) {

    
    int value = -1; // Default return value if flag is not set

    // Read the flag (bytes 4-7)
    int flag = *((int *)((uint8_t *)shm_ptr_new_disc + 4));

    if (flag == 1) {
        // If flag is set, read the value (bytes 0-3)
        value = *((int *)((uint8_t *)shm_ptr_new_disc));

        // Reset the flag (optional, based on your logic)
        *((int *)((uint8_t *)shm_ptr_new_disc + 4)) = 0;  // Reset flag to 0
        printf("Value read from shared memory: %d\n", value);
    } else {
        printf("No new data available in shared memory (flag=0).\n");
    }

    return value;
}








static int player_human(const struct connect4_game *g, void *arg) {
    printf("I'm inside the function player_human\n");
    (void)arg;
    uint64_t taken = g->state[0] | g->state[1];

    int play = -1;
    while (play == -1) { // Wait for a valid move
        play = read_from_shared_memory(shm_ptr_new_disc);
        //play = read_new_disc_from_file(); // Read the move from the .txt file
        
        if (play == -1) {
            sleep(1); // Wait before retrying to avoid busy-waiting
        }
    }
    play--; // Convert to 0-based column index

    if (connect4_valid(taken, play)) {
        return play;
    } else {
        wprintf(L"Invalid move\n");
        return player_human(g, arg); // Retry on invalid move
    }
}


struct ai_config {
    struct connect4_ai *ai;
    uint32_t max_playouts;
};

static int
player_ai(const struct connect4_game *g, void *arg)
{
    struct ai_config *conf = arg;
    if (g->nplays)
        connect4_advance(conf->ai, g->plays[g->nplays - 1]);
    int play = connect4_playout_many(conf->ai, conf->max_playouts);
    connect4_advance(conf->ai, play);
    return play;
}

static char buf[2][CONNECT4_MEMORY_SIZE];  // AI search tree storage
























int main() {


    
    int player_type[2] = {PLAYER_AI, PLAYER_HUMAN};  // Default: AI vs. Human

    //Check for game mode signal
    FILE *file1 = fopen("game_mode.txt", "r");
    if (file1) {
        os_reset_terminal();
        int mode;
        if (fscanf(file1, "%d", &mode) == 1) {
            if (mode == 1) {
                player_type[0] = PLAYER_HUMAN;  // Human vs. AI
                player_type[1] = PLAYER_AI;
            } else if (mode == 2) {
                player_type[0] = PLAYER_AI;  // AI vs. Human
                player_type[1] = PLAYER_HUMAN;
            }
        }
        fclose(file1);
        remove("game_mode.txt");  // Clear the signal file after reading
    }
    
    os_init();
    setlocale(LC_ALL, "");






    printf("Creating shared memory...\n");

    // Create shared memory object
    shm_fd_new_disc = shm_open(SHM_NAME_NEW_DISC, O_CREAT | O_RDWR, 0666);
    if (shm_fd_new_disc == -1) {
        perror("Error creating shared memory");
        exit(EXIT_FAILURE);
    }

    // Resize shared memory object to 8 bytes
    if (ftruncate(shm_fd_new_disc, 8) == -1) {
        perror("Error setting shared memory new disc size");
        shm_unlink(SHM_NAME_NEW_DISC); // Cleanup if resizing fails
        exit(EXIT_FAILURE);
    }

    // Map the shared memory object
    shm_ptr_new_disc = mmap(0, 8, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd_new_disc, 0);
    if (shm_ptr_new_disc == MAP_FAILED) {
        perror("Error mapping shared memory");
        shm_unlink(SHM_NAME_NEW_DISC); // Cleanup if mapping fails
        exit(EXIT_FAILURE);
    }

    printf("Shared memory '%s' created and mapped.\n", SHM_NAME_NEW_DISC);
    // Initialize shared memory to 0
    *((int *)shm_ptr_new_disc) = 0;      // Value
    *((int *)((uint8_t *)shm_ptr_new_disc + 4)) = 0; // Flag








    // Delete any old IPC file if necessary
    delete_bot_move_file();

    // Shared memory setup for bot move communication
    int fd = shm_open(SHM_NAME, O_CREAT | O_RDWR, 0666);
    if (fd == -1) {
        perror("shm_open failed");
        exit(1);
    }

    // Set the size of shared memory
    if (ftruncate(fd, SHM_SIZE) == -1) {
        perror("ftruncate failed");
        exit(1);
    }

    // Map shared memory to the process address space
    int *move_ptr = mmap(NULL, SHM_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (move_ptr == MAP_FAILED) {
        perror("mmap failed");
        exit(1);
    }

    // Initialize game
    int game_over = 0;

     // Main Menu
    int done = 0;
    // Start the game with the selected player types
    printf("Game starting: Player 1: %d, Player 2: %d\n", player_type[0], player_type[1]);
    
    // Initialization
    connect4_startup();
    connect4_player players[2];
    void *args[2];
    struct ai_config ai_config[2];
    for (int i = 0; i < 2; i++) {
        switch (player_type[i]) {
            case PLAYER_HUMAN:
                players[i] = player_human;
                args[i] = NULL;
                break;
            case PLAYER_AI:
                players[i] = player_ai;
                ai_config[i] = (struct ai_config){
                    .ai = connect4_init(buf[i], sizeof(buf[i])),
                    .max_playouts = CONNECT4_MAX_PLAYOUTS,
                };
                args[i] = &ai_config[i];
                break;
        }
    }

    // Game Loop
    struct connect4_game game;
    connect4_game_init(&game);
    printf("connect_run called");
    connect4_game_run(&game, players, args, 1);

    // After the game ends, write the winner to shared memory
   // *(move_ptr+1) = game.winner;  // Store the winner in shared memory (0, 1 for player, -1 for draw)

    // Display the game result
    if (game.winner == -1) {
        wprintf(L"Draw.\n\n");
    } else {
        sleep(2);
        wprintf(L"Player ");
        os_color(game.winner ? COLOR_PLAYER1 : COLOR_PLAYER0);
        fputwc(FULL_BLOCK, stdout);
        os_color(0);
        wprintf(L" wins!\n");
    }
    FILE *file2 = fopen(WINNER_FILE, "w");
    if (file2 == NULL) {
        perror("Failed to open file");
    }
    
    fprintf(file2, "%d\n", game.winner);  // Write the winner (1 or 2)
    fclose(file2);
    printf("Winner %d written to %s\n", game.winner, WINNER_FILE);
    sleep(30);

    // Set shared memory to 255 to signal the end of the game
    *move_ptr = 255;  // Game over signal


        // Cleanup shared memory when done
    if (munmap(move_ptr, SHM_SIZE) == -1) {
        perror("Error unmapping shared memory");
    }

    if (shm_unlink(SHM_NAME) == -1) {
        perror("Error unlinking shared memory");
    }

    if (close(fd) == -1) {
        perror("Error closing shared memory file descriptor");
    } else {
        printf("Shared memory '%s' cleaned up successfully.\n", SHM_NAME_NEW_DISC);
    }

  
  
  
    // Cleanup shared memory when done
    if (munmap(shm_ptr_new_disc, 8) == -1) {
        perror("Error unmapping shared memory");
    }

    if (shm_unlink(SHM_NAME_NEW_DISC) == -1) {
        perror("Error unlinking shared memory");
    }

    if (close(shm_fd_new_disc) == -1) {
        perror("Error closing shared memory file descriptor");
    } else {
        printf("Shared memory '%s' cleaned up successfully.\n", SHM_NAME_NEW_DISC);
    }

    os_finish();
    
    

    return 0;
}
