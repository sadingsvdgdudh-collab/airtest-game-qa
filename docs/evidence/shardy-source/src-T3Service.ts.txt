import { TransportType, Logger, LoggerScope, Tools, Service, Client } from 'shardy';
import { Game } from './Game';

/**
 * Players count to start game
 */
const MAX_PLAYERS_COUNT = 2;

/**
 * Service for Tic-Tac-Toe
 *
 * @export
 * @class T3Service
 * @implements {Service}
 */
export class T3Service implements Service {
  /**
   * List of user
   *
   * @private
   * @type {Map<string, Client>}
   */
  users: Map<string, Client> = new Map<string, Client>();

  /**
   * List of users who search oppenent for play
   *
   * @type {string[]}
   */
  private searchers: string[] = [];

  /**
   * List of active games
   *
   * @type {Game[]}
   */
  private games: Game[] = [];

  /**
   * Timer for example
   *
   * @private
   * @type {NodeJS.Timer}
   */
  private timer!: NodeJS.Timer;

  /**
   * Current service name
   */
  name = process.env.SERVICE_NAME;

  /**
   * Service transport type
   */
  transport = process.env.SERVICE_TRANSPORT as TransportType;

  /**
   * Service logger
   *
   * @private
   * @type {Logger}
   */
  private log: Logger;

  /**
   * Creates an instance of MyService
   */
  constructor() {
    this.log = new Logger([], Tools.getTag(module));
    this.log.info(`initialization`, LoggerScope.System);
  }

  /**
   * Event when new client connected to service
   *
   * @param {Client} client Client instance
   */
  async onConnect(client: Client): Promise<void> {
    this.log.info(`client ${client.id} connected`, LoggerScope.System);
    this.users.set(client.id, client);
  }

  /**
   * Event when new client connected to service
   *
   * @param {Client} client Client instance
   */
  async onReady(client: Client): Promise<void> {
    this.log.info(`client ${client.id} ready`, LoggerScope.System);
  }

  /**
   * Event when client disconnected
   *
   * @param {Client} client
   */
  async onDisconnect(client: Client): Promise<void> {
    this.log.info(`client ${client.id} disconnected`, LoggerScope.System);
    this.users.delete(client.id);
    this.stopSearch(client.id);
  }

  /**
   * Event when service successfully run
   */
  async onListening(host: string, port: number): Promise<void> {
    this.log.info(`listening on ${host}:${port}`, LoggerScope.System);
    this.timer = setInterval(async () => {
      await this.matchPlayers();
    }, 1000);
  }

  /**
   * Event when service get error
   *
   * @param {Error} error Error with data
   */
  async onError(error: Error): Promise<void> {
    this.log.error(`error: ${error}`, LoggerScope.System);
  }

  /**
   * Event when service close
   */
  async onClose(): Promise<void> {
    this.log.info(`closed`, LoggerScope.System);
  }

  /**
   * Start search opponent
   *
   * @async
   * @param {string} id Connection id
   */
  async startSearch(id: string): Promise<void> {
    const index = this.searchers.indexOf(id, 0);
    if (index < 0) {
      this.searchers.push(id);
      this.log.info(`start search: ${id}`);
    }
  }

  /**
   * Stop search opponent
   *
   * @async
   * @param {string} id Connection id
   */
  async stopSearch(id: string): Promise<void> {
    const index = this.searchers.indexOf(id, 0);
    if (index >= 0) {
      this.searchers.splice(index, 1);
      this.log.info(`stop search: ${id}`);
    }
  }

  /**
   * Make turn in game
   *
   * @async
   * @param {string} id Game id
   * @param {number} player Player id
   * @param {number} x X coord
   * @param {number} y Y coord
   */
  async makeTurn(id: string, player: number, x: number, y: number): Promise<void> {
    const game = this.games.find((item) => item.Id === id);
    game?.turn(player, x, y);
  }

  /**
   * Match players and make new games
   *
   * @async
   */
  async matchPlayers(): Promise<void> {
    const list = this.searchers;
    let players: Client[] = [];
    list.forEach((id) => {
      if (this.users.has(id)) {
        players.push(this.users.get(id)!);
      }
      if (players.length == MAX_PLAYERS_COUNT) {
        this.log.info(`players matched: ${players}`);
        players.forEach((item) => {
          this.stopSearch(item.id);
          item.command('play');
        });
        const game = new Game(players);
        this.games.push(game);
        players = [];
        setTimeout(() => {
          game.round();
        }, 2000);
      }
    });
  }

  /**
   * Remove game
   *
   * @async
   * @param {string} id Game id
   */
  async removeGame(id: string): Promise<void> {
    this.games = this.games.filter((item) => item.Id !== id);
    this.log.info(`remove game: ${id}, count: ${this.games.length}`);
  }

  /**
   * Exit from game
   *
   * @async
   * @param {string} id Game id
   * @param {number} player Player index
   */
  async exitGame(id: string, player: number): Promise<void> {
    const game = this.games.find((item) => item.Id === id);
    game?.exit(player);
    this.removeGame(id);
  }
}
